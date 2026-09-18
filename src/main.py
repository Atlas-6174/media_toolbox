import typer
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

from src.core.config import (
    settings,
    resolve_input_file,
    SUPPORTED_BOOK_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS
)
from src.core.docker_runner import DockerRunner, DockerCommandExecutionError, ensure_docker
from src.core.notify import notify, open_directory
from src.tools.calibre import CalibreTool
from src.tools.ffmpeg import FFmpegTool
from src.tools.downloader import DownloaderTool
from src.tools.trimmer import TrimmerTool
from src.tools.gif import GifTool
from src.tools.compressor import VideoCompressorTool
from src.tools.pdf import PdfTool
from src.tools.image import ImageTool

app = typer.Typer(help="📦 Media Toolbox - Suite multimedia CLI con micro-contenedores Docker", rich_markup_mode="rich")
pdf_app = typer.Typer(help="📄 Utilidades para documentos PDF", rich_markup_mode="rich")
app.add_typer(pdf_app, name="pdf")

console = Console()

@app.callback()
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Muestra registros detallados de los contenedores en caso de error")
):
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ensure_docker()

def get_available_files_by_exts(extensions: List[str]):
    found = []
    for ext in extensions:
        clean_ext = ext.lstrip(".")
        found.extend(settings.INPUT_DIR.rglob(f"*.{clean_ext}"))
    return sorted(list(set(found)), key=lambda p: p.name.lower())

def render_files_table(files, category_name: str):
    table = Table(title=f"Archivos {category_name} disponibles en storage/input", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4, justify="center")
    table.add_column("Nombre del archivo", style="cyan")
    table.add_column("Tamaño", style="green", justify="right")

    for idx, f in enumerate(files, start=1):
        size_kb = f.stat().st_size / 1024
        size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
        table.add_row(str(idx), f.name, size_str)
    console.print(table)

def handle_execution_error(e: Exception, ctx: typer.Context, action_name: str):
    console.print(f"\n[bold red]❌ Falló {action_name}[/bold red]")
    if isinstance(e, DockerCommandExecutionError):
        if ctx.obj and ctx.obj.get("verbose") and e.logs:
            console.print("\n[dim]-- Registros de ejecución (logs) --[/dim]")
            for log in e.logs[-20:]:
                console.print(f"[dim]{log.strip()}[/dim]")
        else:
            console.print("[yellow]Usa [bold]--verbose[/bold] o [bold]-v[/bold] para inspeccionar los registros del contenedor.[/yellow]")
    else:
        console.print(f"[red]{e}[/red]")

# ---------------------------------------------------------
# 1. CONVERTIR LIBROS (Calibre)
# ---------------------------------------------------------
@app.command(name="convertir", short_help="Convierte libros digitales (EPUB, MOBI, etc.) a PDF")
def convertir(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del libro"),
    pagina: str = typer.Option("a4", "--pagina", "-p", help="Tamaño de página (a4, letter)"),
    perfil: Optional[str] = typer.Option(None, "--perfil", help="Perfil de lector (kindle, kobo, tablet)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    libros_disponibles = get_available_files_by_exts(SUPPORTED_BOOK_EXTENSIONS)
    archivos_a_procesar = []

    if archivo is None:
        if not libros_disponibles:
            return console.print(Panel("[bold yellow]No hay libros digitales en storage/input/[/bold yellow]"))
        render_files_table(libros_disponibles, "Libros")
        opcion = Prompt.ask("\nIngresa el número del archivo [bold magenta](o '0' para procesar TODOS)[/bold magenta]")
        if opcion == "0":
            archivos_a_procesar = libros_disponibles
        elif opcion.isdigit() and 1 <= int(opcion) <= len(libros_disponibles):
            archivos_a_procesar = [libros_disponibles[int(opcion) - 1]]
        else:
            return console.print("[red]Opción inválida.[/red]")
    else:
        resolved = resolve_input_file(archivo, SUPPORTED_BOOK_EXTENSIONS)
        if not resolved.exists():
            return console.print(f"[red]No se encontró el archivo: {archivo}[/red]")
        archivos_a_procesar = [resolved]

    carpeta_pdfs = settings.OUTPUT_DIR / "pdfs"
    carpeta_pdfs.mkdir(exist_ok=True)

    for libro in archivos_a_procesar:
        out_path = carpeta_pdfs / f"{libro.stem}.pdf"
        try:
            CalibreTool().convert(libro, out_path, paper_size=pagina, output_profile=perfil)
            console.print(f"✨ [bold green]Guardado en:[/bold green] storage/output/pdfs/{out_path.name}")
            notify("Conversión Exitosa", f"{libro.name} convertido a PDF")
        except Exception as e:
            handle_execution_error(e, ctx, f"la conversión de {libro.name}")

    if open_folder:
        open_directory(carpeta_pdfs)

# ---------------------------------------------------------
# 2. EXTRAER AUDIO (FFmpeg)
# ---------------------------------------------------------
@app.command(name="audio", short_help="Extrae pista de audio desde videos")
def extraer_audio(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del video"),
    formato: str = typer.Option("mp3", "--formato", "-f", help="Formato de salida (mp3, wav, m4a)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    videos_disponibles = get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS)
    archivos_a_procesar = []

    if archivo is None:
        if not videos_disponibles:
            return console.print(Panel("[bold yellow]No hay videos en storage/input/[/bold yellow]"))
        render_files_table(videos_disponibles, "Videos")
        opcion = Prompt.ask("\nIngresa el número del archivo [bold cyan](o '0' para procesar TODOS)[/bold cyan]")
        if opcion == "0":
            archivos_a_procesar = videos_disponibles
        elif opcion.isdigit() and 1 <= int(opcion) <= len(videos_disponibles):
            archivos_a_procesar = [videos_disponibles[int(opcion) - 1]]
        else:
            return console.print("[red]Opción inválida.[/red]")
    else:
        resolved = resolve_input_file(archivo, SUPPORTED_VIDEO_EXTENSIONS, subfolder="videos")
        if not resolved.exists():
            return console.print(f"[red]No se encontró el video: {archivo}[/red]")
        archivos_a_procesar = [resolved]

    carpeta_audios = settings.OUTPUT_DIR / "audios"
    carpeta_audios.mkdir(exist_ok=True)
    fmt = formato.lstrip(".").lower()

    for video in archivos_a_procesar:
        out_path = carpeta_audios / f"{video.stem}.{fmt}"
        try:
            FFmpegTool().convert(video, out_path)
            console.print(f"✨ [bold cyan]Guardado en:[/bold cyan] storage/output/audios/{out_path.name}")
            notify("Audio Extraído", f"{video.name} -> {out_path.name}")
        except Exception as e:
            handle_execution_error(e, ctx, f"la extracción de audio de {video.name}")

    if open_folder:
        open_directory(carpeta_audios)

# ---------------------------------------------------------
# 3. DESCARGAR MEDIOS (yt-dlp)
# ---------------------------------------------------------
@app.command(name="descargar", short_help="Descarga videos o audios desde URLs")
def descargar_medio(
    ctx: typer.Context,
    url: Optional[str] = typer.Argument(None, help="URL del video o canción"),
    audio: bool = typer.Option(False, "--audio", "-a", help="Descarga directamente solo el audio"),
    calidad: str = typer.Option("max", "--calidad", "-c", help="Calidad del video (max, 1080p, 720p)"),
    playlist: bool = typer.Option(False, "--playlist", help="Permite descargar listas de reproducción completas"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de descarga al finalizar")
):
    if url is None:
        url = Prompt.ask("\n[bold cyan]Ingresa la URL a descargar[/bold cyan]")
        if not url:
            return console.print("[red]Debes ingresar una URL válida.[/red]")

    destino_dir = settings.INPUT_DIR / ("audios" if audio else "videos")
    destino_dir.mkdir(exist_ok=True)

    try:
        DownloaderTool().descargar(url, solo_audio=audio, calidad=calidad, permitir_playlist=playlist)
        console.print(f"\n✨ [bold green]¡Descarga completada en {destino_dir.name}/![/bold green]\n")
        notify("Descarga Completada", f"Contenido guardado en {destino_dir.name}")
        if open_folder:
            open_directory(destino_dir)
    except Exception as e:
        handle_execution_error(e, ctx, "la descarga multimedia")

# ---------------------------------------------------------
# 4. RECORTAR ARCHIVOS (FFmpeg sin re-encode)
# ---------------------------------------------------------
@app.command(name="recortar", short_help="Recorte ultrarrápido sin pérdida de calidad")
def recortar(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Archivo a recortar"),
    desde: Optional[str] = typer.Option(None, "--desde", "-s", help="Tiempo de inicio (ej. 00:01:00)"),
    hasta: Optional[str] = typer.Option(None, "--hasta", "-e", help="Tiempo final (ej. 00:02:30)"),
    duracion: Optional[str] = typer.Option(None, "--duracion", "-d", help="Duración del corte (ej. 30s)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    if not archivo:
        videos = get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS)
        if not videos:
            return console.print("[yellow]No hay archivos para recortar en storage/input/[/yellow]")
        render_files_table(videos, "Multimedia")
        opcion = Prompt.ask("\nIngresa el número del archivo")
        if opcion.isdigit() and 1 <= int(opcion) <= len(videos):
            archivo_path = videos[int(opcion) - 1]
        else:
            return console.print("[red]Opción inválida.[/red]")
    else:
        archivo_path = resolve_input_file(archivo)

    if not desde and not hasta and not duracion:
        desde = Prompt.ask("Punto de inicio (ej. 00:00:10)", default="00:00:00")
        hasta = Prompt.ask("Punto de fin (ej. 00:00:30)", default="")

    carpeta_recortes = settings.OUTPUT_DIR / "recortes"
    carpeta_recortes.mkdir(exist_ok=True)
    out_path = carpeta_recortes / f"{archivo_path.stem}_recorte{archivo_path.suffix}"

    try:
        TrimmerTool().trim(archivo_path, out_path, desde=desde, hasta=hasta, duracion=duracion)
        console.print(f"✨ [bold green]Recorte guardado en:[/bold green] storage/output/recortes/{out_path.name}")
        notify("Recorte Finalizado", out_path.name)
        if open_folder:
            open_directory(carpeta_recortes)
    except Exception as e:
        handle_execution_error(e, ctx, f"el recorte de {archivo_path.name}")

# ---------------------------------------------------------
# 5. GENERAR GIF (FFmpeg)
# ---------------------------------------------------------
@app.command(name="gif", short_help="Convierte video en GIF animado de alta fidelidad")
def crear_gif(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Video de origen"),
    desde: Optional[str] = typer.Option(None, "--desde", "-s", help="Tiempo de inicio (ej. 00:00:05)"),
    hasta: Optional[str] = typer.Option(None, "--hasta", "-e", help="Tiempo de final"),
    duracion: Optional[str] = typer.Option("5s", "--duracion", "-d", help="Duración del GIF (ej. 5s)"),
    fps: int = typer.Option(15, "--fps", help="Cuadros por segundo"),
    ancho: int = typer.Option(480, "--ancho", "-w", help="Ancho en píxeles"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    if not archivo:
        videos = get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS)
        if not videos:
            return console.print("[yellow]No hay videos en storage/input/[/yellow]")
        render_files_table(videos, "Videos")
        opcion = Prompt.ask("\nIngresa el número del archivo")
        if opcion.isdigit() and 1 <= int(opcion) <= len(videos):
            archivo_path = videos[int(opcion) - 1]
        else:
            return console.print("[red]Opción inválida.[/red]")
    else:
        archivo_path = resolve_input_file(archivo, SUPPORTED_VIDEO_EXTENSIONS)

    carpeta_gifs = settings.OUTPUT_DIR / "gifs"
    carpeta_gifs.mkdir(exist_ok=True)
    out_path = carpeta_gifs / f"{archivo_path.stem}.gif"

    try:
        GifTool().create_gif(archivo_path, out_path, desde=desde, hasta=hasta, duracion=duracion, fps=fps, ancho=ancho)
        console.print(f"✨ [bold green]GIF guardado en:[/bold green] storage/output/gifs/{out_path.name}")
        notify("GIF Generado", out_path.name)
        if open_folder:
            open_directory(carpeta_gifs)
    except Exception as e:
        handle_execution_error(e, ctx, f"la creación de GIF de {archivo_path.name}")

# ---------------------------------------------------------
# 6. COMPRIMIR VIDEO (FFmpeg)
# ---------------------------------------------------------
@app.command(name="comprimir", short_help="Reduce el peso de videos con compresión inteligente")
def comprimir_video(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Video a comprimir"),
    perfil: str = typer.Option("equilibrada", "--perfil", "-p", help="Perfil: ligera, equilibrada, maxima"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    if not archivo:
        videos = get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS)
        if not videos:
            return console.print("[yellow]No hay videos en storage/input/[/yellow]")
        render_files_table(videos, "Videos")
        opcion = Prompt.ask("\nIngresa el número del archivo")
        if opcion.isdigit() and 1 <= int(opcion) <= len(videos):
            archivo_path = videos[int(opcion) - 1]
        else:
            return console.print("[red]Opción inválida.[/red]")
    else:
        archivo_path = resolve_input_file(archivo, SUPPORTED_VIDEO_EXTENSIONS)

    carpeta_comprimidos = settings.OUTPUT_DIR / "comprimidos"
    carpeta_comprimidos.mkdir(exist_ok=True)
    out_path = carpeta_comprimidos / f"{archivo_path.stem}_comprimido.mp4"

    try:
        VideoCompressorTool().compress(archivo_path, out_path, perfil=perfil)
        console.print(f"✨ [bold green]Video comprimido en:[/bold green] storage/output/comprimidos/{out_path.name}")
        notify("Compresión Finalizada", out_path.name)
        if open_folder:
            open_directory(carpeta_comprimidos)
    except Exception as e:
        handle_execution_error(e, ctx, f"la compresión de {archivo_path.name}")

# ---------------------------------------------------------
# 7. UTILIDADES PDF (pdfunite)
# ---------------------------------------------------------
@pdf_app.command(name="unir", short_help="Une múltiples archivos PDF en uno solo")
def unir_pdfs(
    ctx: typer.Context,
    archivos: Optional[List[str]] = typer.Argument(None, help="Lista de PDFs a unir"),
    salida: str = typer.Option("documento_unido.pdf", "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    if not archivos:
        disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")) + list(settings.OUTPUT_DIR.rglob("*.pdf")))
        if len(disponibles) < 2:
            return console.print("[yellow]Se necesitan al menos 2 PDFs en storage/ para unirlos.[/yellow]")
        render_files_table(disponibles, "PDFs")
        seleccion = Prompt.ask("\nIngresa los números separados por comas (ej. 1, 2)")
        indices = [int(i.strip()) - 1 for i in seleccion.split(",") if i.strip().isdigit()]
        archivos_finales = [disponibles[i] for i in indices if 0 <= i < len(disponibles)]
    else:
        archivos_finales = [resolve_input_file(a, [".pdf"]) for a in archivos]

    if len(archivos_finales) < 2:
        return console.print("[red]Debes especificar al menos 2 archivos PDF para unir.[/red]")

    carpeta_pdfs = settings.OUTPUT_DIR / "pdfs"
    carpeta_pdfs.mkdir(exist_ok=True)
    out_path = carpeta_pdfs / (salida if salida.endswith(".pdf") else f"{salida}.pdf")

    try:
        PdfTool().unir(archivos_finales, out_path)
        console.print(f"✨ [bold green]PDFs unidos en:[/bold green] storage/output/pdfs/{out_path.name}")
        notify("PDFs Unidos", out_path.name)
        if open_folder:
            open_directory(carpeta_pdfs)
    except Exception as e:
        handle_execution_error(e, ctx, "la unión de PDFs")

# ---------------------------------------------------------
# 8. CONVERSIÓN DE IMÁGENES (FFmpeg WebP)
# ---------------------------------------------------------
@app.command(name="imagen", short_help="Convierte y optimiza imágenes a WebP, JPG o PNG")
def convertir_imagen(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Imagen de origen"),
    formato: str = typer.Option("webp", "--formato", "-f", help="Formato de salida (webp, jpg, png)"),
    calidad: int = typer.Option(80, "--calidad", "-q", help="Calidad de salida (1-100)"),
    ancho: Optional[int] = typer.Option(None, "--ancho", "-w", help="Redimensionar ancho en píxeles"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar")
):
    if not archivo:
        imagenes = get_available_files_by_exts(SUPPORTED_IMAGE_EXTENSIONS)
        if not imagenes:
            return console.print("[yellow]No hay imágenes en storage/input/[/yellow]")
        render_files_table(imagenes, "Imágenes")
        opcion = Prompt.ask("\nIngresa el número del archivo")
        if opcion.isdigit() and 1 <= int(opcion) <= len(imagenes):
            archivo_path = imagenes[int(opcion) - 1]
        else:
            return console.print("[red]Opción inválida.[/red]")
    else:
        archivo_path = resolve_input_file(archivo, SUPPORTED_IMAGE_EXTENSIONS)

    carpeta_img = settings.OUTPUT_DIR / "imagenes"
    carpeta_img.mkdir(exist_ok=True)
    fmt = formato.lstrip(".").lower()
    out_path = carpeta_img / f"{archivo_path.stem}.{fmt}"

    try:
        ImageTool().convert(archivo_path, out_path, calidad=calidad, ancho=ancho)
        console.print(f"✨ [bold green]Imagen guardada en:[/bold green] storage/output/imagenes/{out_path.name}")
        notify("Imagen Optimizada", out_path.name)
        if open_folder:
            open_directory(carpeta_img)
    except Exception as e:
        handle_execution_error(e, ctx, f"la optimización de {archivo_path.name}")

# ---------------------------------------------------------
# 9. ESTADO DEL SISTEMA (tb estado)
# ---------------------------------------------------------
@app.command(name="estado", short_help="Muestra el estado del almacenamiento y recursos de Docker")
def mostrar_estado():
    def get_dir_size(path: Path):
        total = 0
        count = 0
        if path.exists():
            for p in path.rglob("*"):
                if p.is_file() and p.name != ".gitkeep" and p.name != ".DS_Store":
                    total += p.stat().st_size
                    count += 1
        return total, count

    in_size, in_count = get_dir_size(settings.INPUT_DIR)
    out_size, out_count = get_dir_size(settings.OUTPUT_DIR)

    table = Table(title="📊 Estado de Almacenamiento (storage/)", header_style="bold green")
    table.add_column("Carpeta", style="cyan")
    table.add_column("Archivos", justify="center")
    table.add_column("Espacio Ocupado", justify="right", style="magenta")

    table.add_row("storage/input (Entrada)", str(in_count), f"{in_size / (1024*1024):.2f} MB")
    table.add_row("storage/output (Salida)", str(out_count), f"{out_size / (1024*1024):.2f} MB")
    console.print(table)

    # Estado de contenedores
    console.print("\n[bold cyan]🐳 Imágenes de Docker asociadas:[/bold cyan]")
    try:
        import subprocess
        res = subprocess.run(
            ["docker", "images", "--filter=reference=local/toolbox-calibre*", "--filter=reference=*ffmpeg*", "--filter=reference=*yt-dlp*", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}"],
            capture_output=True, text=True, timeout=3
        )
        if res.stdout.strip():
            img_table = Table(show_header=True, header_style="bold blue")
            img_table.add_column("Imagen")
            img_table.add_column("Tamaño", justify="right")
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    img_table.add_row(parts[0], parts[1] if len(parts) > 1 else "N/A")
            console.print(img_table)
        else:
            console.print("[dim]No se detectaron imágenes descargadas aún.[/dim]")
    except Exception:
        console.print("[dim]No fue posible consultar imágenes de Docker.[/dim]")

if __name__ == "__main__":
    app()