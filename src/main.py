from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.core.config import (
    SUPPORTED_BOOK_EXTENSIONS,
    SUPPORTED_DESIGN_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    resolve_input_file,
    settings,
)
from src.core.docker_runner import DockerCommandExecutionError
from src.core.notify import notify, open_directory
from src.tools.calibre import CalibreTool
from src.tools.cmyk import CmykTool
from src.tools.compressor import VideoCompressorTool
from src.tools.downloader import DownloaderTool
from src.tools.ffmpeg import FFmpegTool
from src.tools.gif import GifTool
from src.tools.image import ImageTool
from src.tools.pdf import PdfTool
from src.tools.privacy import PrivacyTool
from src.tools.trimmer import TrimmerTool

app = typer.Typer(help="📦 Media Toolbox - Suite multimedia CLI con micro-contenedores Docker", rich_markup_mode="rich")
pdf_app = typer.Typer(help="📄 Utilidades para documentos PDF", rich_markup_mode="rich")
app.add_typer(pdf_app, name="pdf")

console = Console()


@app.callback()
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Muestra registros detallados de los contenedores en caso de error"
    ),
):
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


def get_available_files_by_exts(extensions: List[str]) -> List[Path]:
    found: List[Path] = []
    for ext in extensions:
        clean_ext = ext.lstrip(".")
        found.extend(settings.INPUT_DIR.rglob(f"*.{clean_ext}"))
    return sorted(list(set(found)), key=lambda p: p.name.lower())


def render_files_table(files, category_name: str):
    table = Table(
        title=f"Archivos {category_name} disponibles en storage/input", show_header=True, header_style="bold magenta"
    )
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
            console.print(
                "[yellow]Usa [bold]--verbose[/bold] o [bold]-v[/bold] para inspeccionar los registros del contenedor.[/yellow]"
            )
    else:
        console.print(f"[red]{e}[/red]")


def select_single_file(
    archivo: Optional[str],
    candidates: List[Path],
    category_label: str,
    empty_message: str,
    extensions: Optional[List[str]] = None,
    subfolder: str = "",
    default: str = "1",
) -> Optional[Path]:
    """
    Resuelve un único archivo a procesar.
    Si `archivo` viene dado, lo resuelve directamente (importándolo si es una ruta externa).
    Si no, muestra `candidates` en una tabla y pide al usuario elegir por número.
    Devuelve None (imprimiendo el mensaje correspondiente) si no hay una selección válida.
    """
    if archivo:
        return resolve_input_file(archivo, extensions, subfolder=subfolder)

    if not candidates:
        console.print(f"[yellow]{empty_message}[/yellow]")
        return None

    render_files_table(candidates, category_label)
    seleccion = Prompt.ask("\nIngresa el número del archivo", default=default)
    try:
        idx = int(seleccion) - 1
    except ValueError:
        idx = -1
    if 0 <= idx < len(candidates):
        return candidates[idx]
    console.print("[red]Selección inválida.[/red]")
    return None


def select_files_or_all(
    archivo: Optional[str],
    candidates: List[Path],
    category_label: str,
    empty_message: str,
    extensions: Optional[List[str]] = None,
    subfolder: str = "",
    prompt_color: str = "cyan",
) -> List[Path]:
    """
    Resuelve la lista de archivos a procesar en lote.
    Si `archivo` viene dado, resuelve ese único archivo (validando que exista).
    Si no, permite elegir uno de `candidates` o '0' para procesarlos todos.
    Devuelve una lista vacía (imprimiendo el mensaje correspondiente) si no hay selección válida.
    """
    if archivo:
        resolved = resolve_input_file(archivo, extensions, subfolder=subfolder)
        if not resolved.exists():
            console.print(f"[red]No se encontró el archivo: {archivo}[/red]")
            return []
        return [resolved]

    if not candidates:
        console.print(Panel(f"[bold yellow]{empty_message}[/bold yellow]"))
        return []

    render_files_table(candidates, category_label)
    opcion = Prompt.ask(
        f"\nIngresa el número del archivo [bold {prompt_color}](o '0' para procesar TODOS)[/bold {prompt_color}]"
    )
    if opcion == "0":
        return candidates
    if opcion.isdigit() and 1 <= int(opcion) <= len(candidates):
        return [candidates[int(opcion) - 1]]
    console.print("[red]Opción inválida.[/red]")
    return []


# ---------------------------------------------------------
# 1. CONVERTIR LIBROS (Calibre)
# ---------------------------------------------------------
@app.command(name="convertir", short_help="Convierte libros digitales (EPUB, MOBI, etc.) a PDF")
def convertir(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del libro"),
    pagina: str = typer.Option("a4", "--pagina", "-p", help="Tamaño de página (a4, letter)"),
    perfil: Optional[str] = typer.Option(None, "--perfil", help="Perfil de lector (kindle, kobo, tablet)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    archivos_a_procesar = select_files_or_all(
        archivo,
        get_available_files_by_exts(SUPPORTED_BOOK_EXTENSIONS),
        "Libros",
        "No hay libros digitales en storage/input/",
        extensions=SUPPORTED_BOOK_EXTENSIONS,
        prompt_color="magenta",
    )
    if not archivos_a_procesar:
        return

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
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    archivos_a_procesar = select_files_or_all(
        archivo,
        get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS),
        "Videos",
        "No hay videos en storage/input/",
        extensions=SUPPORTED_VIDEO_EXTENSIONS,
        subfolder="videos",
        prompt_color="cyan",
    )
    if not archivos_a_procesar:
        return

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
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de descarga al finalizar"),
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
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS),
        "Multimedia",
        "No hay archivos para recortar en storage/input/",
    )
    if archivo_path is None:
        return

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
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS),
        "Videos",
        "No hay videos en storage/input/",
        extensions=SUPPORTED_VIDEO_EXTENSIONS,
    )
    if archivo_path is None:
        return

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
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS),
        "Videos",
        "No hay videos en storage/input/",
        extensions=SUPPORTED_VIDEO_EXTENSIONS,
    )
    if archivo_path is None:
        return

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
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
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


@pdf_app.command(name="comprimir", short_help="Comprime y optimiza el tamaño de un archivo PDF")
def comprimir_pdf(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo PDF"),
    perfil: str = typer.Option(
        "ebook",
        "--perfil",
        "-p",
        help="Calidad: screen (máxima reducción), ebook (equilibrada), printer (alta calidad)",
    ),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Comprime y optimiza el tamaño de un archivo PDF usando Ghostscript."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")) + list(settings.OUTPUT_DIR.rglob("*.pdf")))
    archivo_path = select_single_file(
        archivo, disponibles, "PDFs", "No hay archivos PDF en storage/ para comprimir.", extensions=[".pdf"]
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "pdf_comprimidos"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"{archivo_path.stem}_comprimido.pdf"
    if not out_name.endswith(".pdf"):
        out_name += ".pdf"
    out_path = carpeta_salida / out_name

    try:
        stats = PdfTool().compress(archivo_path, out_path, perfil=perfil)
        orig_mb = stats["input_size"] / (1024 * 1024)
        new_mb = stats["output_size"] / (1024 * 1024)

        if stats.get("was_already_optimal"):
            console.print(f"ℹ️ [yellow]El PDF ya se encontraba en su tamaño óptimo ({orig_mb:.2f} MB). Se conservó el archivo original.[/yellow]")
        else:
            console.print(f"✨ [bold green]PDF comprimido en:[/bold green] storage/output/pdf_comprimidos/{out_path.name}")
            console.print(f"📉 [dim]Tamaño: {orig_mb:.2f} MB -> {new_mb:.2f} MB ({stats['saved_pct']}% reducción)[/dim]")
        notify("PDF Comprimido", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la compresión de {archivo_path.name}")


@pdf_app.command(name="ocr", short_help="Añade texto seleccionable a un PDF escaneado con OCR (Tesseract)")
def ocr_pdf_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo PDF"),
    idioma: str = typer.Option("spa+eng", "--idioma", "-l", help="Idioma OCR (spa, eng, fra, deu o combinaciones con +)"),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Ejecuta OCR sobre un PDF escaneado para hacer que el texto sea buscable y seleccionable."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")))
    archivo_path = select_single_file(
        archivo, disponibles, "PDFs", "No hay archivos PDF en storage/input/ para OCR.", extensions=[".pdf"]
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "pdfs"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"{archivo_path.stem}_ocr.pdf"
    if not out_name.endswith(".pdf"):
        out_name += ".pdf"
    out_path = carpeta_salida / out_name

    try:
        console.print(f"[bold cyan]🔍 Procesando OCR ({idioma}) con Tesseract en contenedor Docker...[/bold cyan]")
        PdfTool().ocr(archivo_path, out_path, idioma=idioma)
        console.print(f"✨ [bold green]PDF con OCR listo en:[/bold green] storage/output/pdfs/{out_path.name}")
        notify("OCR Completado", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"el OCR de {archivo_path.name}")


@pdf_app.command(name="extraer", short_help="Extrae un rango de páginas de un PDF (ej. 1-5, 3,7)")
def extraer_paginas_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo PDF"),
    paginas: str = typer.Option("1", "--paginas", "-p", help="Rango o lista de páginas (ej. 1-5, 1-3,8, 5-z)"),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Extrae páginas específicas de un PDF usando qpdf sin perder calidad."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")))
    archivo_path = select_single_file(
        archivo, disponibles, "PDFs", "No hay archivos PDF en storage/input/.", extensions=[".pdf"]
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "pdfs"
    carpeta_salida.mkdir(exist_ok=True)
    clean_p = paginas.replace(" ", "")
    out_name = salida if salida else f"{archivo_path.stem}_p{clean_p}.pdf"
    if not out_name.endswith(".pdf"):
        out_name += ".pdf"
    out_path = carpeta_salida / out_name

    try:
        console.print(f"[bold cyan]✂️ Extrayendo páginas '{paginas}' con qpdf...[/bold cyan]")
        PdfTool().extract_pages(archivo_path, out_path, paginas=clean_p)
        console.print(f"✨ [bold green]Páginas extraídas en:[/bold green] storage/output/pdfs/{out_path.name}")
        notify("Páginas Extraídas", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la extracción de páginas de {archivo_path.name}")


@pdf_app.command(name="imagenes", short_help="Convierte cada página del PDF en imágenes PNG o JPG")
def pdf_a_imagenes_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo PDF"),
    formato: str = typer.Option("png", "--formato", "-f", help="Formato de imagen (png, jpg, tiff)"),
    dpi: int = typer.Option(300, "--dpi", "-d", help="Resolución en DPI (ej. 150, 300)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Convierte un PDF completo en imágenes de alta resolución con pdftoppm."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")))
    archivo_path = select_single_file(
        archivo, disponibles, "PDFs", "No hay archivos PDF en storage/input/.", extensions=[".pdf"]
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "imagenes" / archivo_path.stem
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    try:
        console.print(f"[bold cyan]🖼️ Renderizando páginas a {formato.upper()} ({dpi} DPI)...[/bold cyan]")
        imgs = PdfTool().pdf_to_images(archivo_path, carpeta_salida, formato=formato, dpi=dpi)
        console.print(f"✨ [bold green]¡{len(imgs)} páginas guardadas en:[/bold green] storage/output/imagenes/{archivo_path.stem}/")
        notify("PDF a Imágenes", f"{len(imgs)} imágenes creadas")
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la conversión a imágenes de {archivo_path.name}")


@pdf_app.command(name="markdown", short_help="Convierte un documento a Markdown usando markitdown (PDF, DOCX, PPTX, XLSX, HTML...)")
def pdf_a_markdown_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Ruta o nombre del archivo a convertir"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """
    Convierte documentos de múltiples formatos a Markdown usando markitdown.
    Soporta: PDF, DOCX, PPTX, XLSX, XLS, HTML, CSV, EPUB, TXT, ZIP e imágenes.
    """
    from src.tools.markdown_tool import MarkdownTool

    SUPPORTED_EXTS = MarkdownTool.SUPPORTED_EXTENSIONS
    disponibles = [f for f in settings.INPUT_DIR.rglob("*") if f.suffix.lower() in SUPPORTED_EXTS]
    archivo_path = select_single_file(
        archivo, disponibles, "Documentos", "No hay archivos compatibles en storage/input/.", extensions=SUPPORTED_EXTS
    )
    if archivo_path is None:
        return

    out_dir = settings.OUTPUT_DIR / "markdown"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{archivo_path.stem}.md"

    try:
        console.print(f"[bold cyan]✦ Convirtiendo '{archivo_path.name}' a Markdown...[/bold cyan]")
        result = MarkdownTool().convert(archivo_path, output_path)
        char_count = len(result.read_text(encoding="utf-8"))
        console.print(f"✨ [bold green]¡Conversión completada![/bold green] {char_count:,} caracteres → storage/output/markdown/{result.name}")
        notify("Markdown generado", f"{archivo_path.name} → {result.name}")
        if open_folder:
            open_directory(out_dir)
    except ImportError:
        console.print("[red]markitdown no está instalado. Instala con: pip install 'markitdown[pdf,docx,pptx,xlsx]'[/red]")
    except Exception as e:
        handle_execution_error(e, ctx, f"la conversión de {archivo_path.name}")


@pdf_app.command(name="rotar", short_help="Rota las páginas de un PDF (90, 180 o 270 grados)")
def rotar_pdf_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo PDF"),
    angulo: int = typer.Option(90, "--angulo", "-a", help="Ángulo de rotación (90, 180, 270 o -90)"),
    paginas: str = typer.Option("1-z", "--paginas", "-p", help="Rango de páginas a rotar (ej. 1-3, todas por defecto)"),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Rota páginas de un PDF usando qpdf, sin pérdida de calidad."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")))
    archivo_path = select_single_file(
        archivo, disponibles, "PDFs", "No hay archivos PDF en storage/input/.", extensions=[".pdf"]
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "pdfs"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"{archivo_path.stem}_rotado.pdf"
    if not out_name.endswith(".pdf"):
        out_name += ".pdf"
    out_path = carpeta_salida / out_name

    try:
        PdfTool().rotate(archivo_path, out_path, angulo=angulo, paginas=paginas)
        console.print(f"✨ [bold green]PDF rotado en:[/bold green] storage/output/pdfs/{out_path.name}")
        notify("PDF Rotado", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la rotación de {archivo_path.name}")


@pdf_app.command(name="proteger", short_help="Protege un PDF con contraseña (cifrado AES-256)")
def proteger_pdf_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo PDF"),
    password: str = typer.Option(..., "--password", "-w", prompt=True, hide_input=True, help="Contraseña para abrir el PDF"),
    password_propietario: Optional[str] = typer.Option(
        None, "--password-propietario", help="Contraseña de propietario (permisos); si se omite, usa la misma"
    ),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Protege un PDF con contraseña usando cifrado AES-256 (qpdf)."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.pdf")))
    archivo_path = select_single_file(
        archivo, disponibles, "PDFs", "No hay archivos PDF en storage/input/.", extensions=[".pdf"]
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "pdfs"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"{archivo_path.stem}_protegido.pdf"
    if not out_name.endswith(".pdf"):
        out_name += ".pdf"
    out_path = carpeta_salida / out_name

    try:
        PdfTool().protect(archivo_path, out_path, password_usuario=password, password_propietario=password_propietario)
        console.print(f"🔒 [bold green]PDF protegido en:[/bold green] storage/output/pdfs/{out_path.name}")
        notify("PDF Protegido", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la protección de {archivo_path.name}")


@pdf_app.command(name="desde-office", short_help="Convierte documentos de oficina (Word/Excel/PowerPoint) a PDF")
def office_a_pdf_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del documento (docx, xlsx, pptx, odt...)"),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Convierte documentos de oficina a PDF manteniendo el formato visual, usando LibreOffice headless."""
    from src.tools.office import SUPPORTED_OFFICE_EXTENSIONS, OfficeTool

    disponibles = [f for f in settings.INPUT_DIR.rglob("*") if f.suffix.lower() in SUPPORTED_OFFICE_EXTENSIONS]
    archivo_path = select_single_file(
        archivo,
        disponibles,
        "Documentos de oficina",
        "No hay documentos de oficina (docx, xlsx, pptx...) en storage/input/.",
        extensions=SUPPORTED_OFFICE_EXTENSIONS,
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "pdfs"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"{archivo_path.stem}.pdf"
    if not out_name.endswith(".pdf"):
        out_name += ".pdf"
    out_path = carpeta_salida / out_name

    try:
        console.print(f"[bold cyan]📄 Convirtiendo '{archivo_path.name}' a PDF con LibreOffice...[/bold cyan]")
        OfficeTool().convert_to_pdf(archivo_path, out_path)
        console.print(f"✨ [bold green]PDF generado en:[/bold green] storage/output/pdfs/{out_path.name}")
        notify("Documento Convertido a PDF", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la conversión a PDF de {archivo_path.name}")


# ---------------------------------------------------------
# 8. CONVERSIÓN DE IMÁGENES (FFmpeg WebP / heif-convert)
# ---------------------------------------------------------
@app.command(name="imagen", short_help="Convierte y optimiza imágenes a WebP, JPG o PNG (soporta HEIC)")
def convertir_imagen(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Imagen de origen"),
    formato: str = typer.Option("webp", "--formato", "-f", help="Formato de salida (webp, jpg, png)"),
    calidad: int = typer.Option(80, "--calidad", "-q", help="Calidad de salida (1-100)"),
    ancho: Optional[int] = typer.Option(None, "--ancho", "-w", help="Redimensionar ancho en píxeles"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_IMAGE_EXTENSIONS),
        "Imágenes",
        "No hay imágenes en storage/input/",
        extensions=SUPPORTED_IMAGE_EXTENSIONS,
    )
    if archivo_path is None:
        return

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
# 9. SEGURIDAD Y PRIVACIDAD DE METADATOS (MAT2)
# ---------------------------------------------------------
@app.command(name="limpiar", short_help="Elimina metadatos y rastros de privacidad usando MAT2")
def limpiar_metadatos(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del archivo a limpiar"),
    inspeccionar: bool = typer.Option(
        False, "--inspeccionar", "-i", help="Solo inspecciona y muestra los metadatos sin modificar el archivo"
    ),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Elimina metadatos y rastros de privacidad usando MAT2."""
    disponibles = sorted(
        [p for p in settings.INPUT_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep" and p.name != ".DS_Store"]
    )
    archivo_path = select_single_file(
        archivo, disponibles, "archivos", "No hay archivos en storage/input/ para procesar."
    )
    if archivo_path is None:
        return

    tool = PrivacyTool()
    if inspeccionar:
        try:
            meta = tool.inspect(archivo_path)
            console.print(
                Panel(f"[bold cyan]Metadatos detectados en {archivo_path.name}:[/bold cyan]", title="🛡️ MAT2 Inspector")
            )
            if not meta:
                console.print("[green]No se detectaron metadatos sensibles conocidos.[/green]")
            else:
                for k, v in meta.items():
                    console.print(f"  [bold]{k}:[/bold] {v}")
        except Exception as e:
            handle_execution_error(e, ctx, f"la inspección de {archivo_path.name}")
        return

    carpeta_salida = settings.OUTPUT_DIR / "limpios"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"limpio_{archivo_path.name}"
    out_path = carpeta_salida / out_name

    try:
        tool.clean(archivo_path, out_path)
        console.print(
            f"🛡️ [bold green]Archivo limpiado y anonimizado en:[/bold green] storage/output/limpios/{out_path.name}"
        )
        notify("Metadatos Eliminados", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la limpieza de {archivo_path.name}")


app.command(name="privacidad", short_help="Alias de 'limpiar'")(limpiar_metadatos)


# ---------------------------------------------------------
# 10. PRENSA Y EXPORTACIÓN CMYK (Inkscape / Ghostscript)
# ---------------------------------------------------------
@app.command(name="cmyk", short_help="Convierte ilustraciones de Inkscape (SVG), PDF e imágenes a CMYK para imprenta")
def convertir_cmyk(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Nombre o ruta del diseño (SVG, PDF, PNG, JPG)"),
    formato: str = typer.Option(
        "pdf", "--formato", "-f", help="Formato de salida: pdf (vectorial), tiff (300 DPI), jpg (300 DPI)"
    ),
    perfil: str = typer.Option("fogra39", "--perfil", "-p", help="Perfil de color: fogra39, swop, generico"),
    dpi: int = typer.Option(300, "--dpi", "-d", help="Resolución en DPI para mapa de bits (300, 600, 150)"),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Convierte ilustraciones y diseños de RGB a CMYK puro para imprenta profesional."""
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_DESIGN_EXTENSIONS),
        "Diseños",
        "No hay diseños (SVG, PDF o imágenes) en storage/input/",
        extensions=SUPPORTED_DESIGN_EXTENSIONS,
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "cmyk"
    carpeta_salida.mkdir(exist_ok=True)
    fmt = formato.lstrip(".").lower()
    ext_out = "pdf" if fmt == "pdf" else ("tif" if fmt in ["tiff", "tif"] else "jpg")
    out_name = salida if salida else f"{archivo_path.stem}_cmyk.{ext_out}"
    if not out_name.endswith(f".{ext_out}"):
        out_name += f".{ext_out}"
    out_path = carpeta_salida / out_name

    try:
        CmykTool().convert(archivo_path, out_path, formato=fmt, perfil=perfil, dpi=dpi)
        console.print(
            f"🖨️ [bold green]Diseño CMYK listo para imprenta en:[/bold green] storage/output/cmyk/{out_path.name}"
        )
        notify("Diseño CMYK Listo", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la exportación a CMYK de {archivo_path.name}")


app.command(name="imprenta", short_help="Alias de 'cmyk'")(convertir_cmyk)


# ---------------------------------------------------------
# 11. MARCA DE AGUA (ImageMagick / FFmpeg)
# ---------------------------------------------------------
@app.command(name="marca-agua", short_help="Superpone una marca de agua de texto o logo en una imagen o video")
def marca_agua_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Imagen o video de origen"),
    texto: Optional[str] = typer.Option(None, "--texto", "-t", help="Texto de la marca de agua"),
    logo: Optional[str] = typer.Option(None, "--logo", "-l", help="Ruta a una imagen (logo) para usar como marca de agua"),
    posicion: str = typer.Option(
        "bottomright", "--posicion", "-p", help="Posición: bottomright, bottomleft, topright, topleft, center"
    ),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Superpone texto o un logo sobre una imagen o video. Detecta automáticamente el tipo de archivo."""
    exts_combinadas = SUPPORTED_IMAGE_EXTENSIONS + SUPPORTED_VIDEO_EXTENSIONS
    candidatos = get_available_files_by_exts(exts_combinadas)
    archivo_path = select_single_file(
        archivo, candidatos, "Imágenes / Videos", "No hay imágenes ni videos en storage/input/.", extensions=exts_combinadas
    )
    if archivo_path is None:
        return

    if not texto and not logo:
        texto = Prompt.ask("Texto de la marca de agua", default="MediaBox")

    logo_path = resolve_input_file(logo, SUPPORTED_IMAGE_EXTENSIONS) if logo else None
    carpeta_salida = settings.OUTPUT_DIR / "marcas_agua"
    carpeta_salida.mkdir(exist_ok=True)
    es_video = archivo_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    out_path = carpeta_salida / f"{archivo_path.stem}_wm{archivo_path.suffix}"

    try:
        if es_video:
            FFmpegTool().watermark(archivo_path, out_path, texto=texto, logo_file=logo_path, posicion=posicion)
        else:
            ImageTool().watermark(archivo_path, out_path, texto=texto, logo_file=logo_path, posicion=posicion)
        console.print(f"✨ [bold green]Marca de agua aplicada en:[/bold green] storage/output/marcas_agua/{out_path.name}")
        notify("Marca de Agua Aplicada", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la marca de agua de {archivo_path.name}")


# ---------------------------------------------------------
# 12. SUBTÍTULOS (FFmpeg)
# ---------------------------------------------------------
subtitulos_app = typer.Typer(help="💬 Extraer o incrustar subtítulos en video", rich_markup_mode="rich")
app.add_typer(subtitulos_app, name="subtitulos")


@subtitulos_app.command(name="extraer", short_help="Extrae una pista de subtítulos de un video a un archivo .srt")
def extraer_subtitulos_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Video de origen"),
    pista: int = typer.Option(0, "--pista", "-t", help="Índice de la pista de subtítulos (0 = primera)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Extrae una pista de subtítulos embebida en un video a un archivo .srt independiente."""
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS),
        "Videos",
        "No hay videos en storage/input/",
        extensions=SUPPORTED_VIDEO_EXTENSIONS,
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "subtitulos"
    carpeta_salida.mkdir(exist_ok=True)
    out_path = carpeta_salida / f"{archivo_path.stem}.srt"

    try:
        FFmpegTool().extract_subtitles(archivo_path, out_path, pista=pista)
        console.print(f"✨ [bold green]Subtítulos extraídos en:[/bold green] storage/output/subtitulos/{out_path.name}")
        notify("Subtítulos Extraídos", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la extracción de subtítulos de {archivo_path.name}")


@subtitulos_app.command(name="quemar", short_help="Incrusta ('quema') subtítulos directamente sobre el video")
def quemar_subtitulos_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Video de origen"),
    subtitulo: str = typer.Argument(..., help="Archivo de subtítulos (.srt, .ass, .vtt)"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Incrusta una pista de subtítulos directamente en la imagen del video (visible en cualquier reproductor)."""
    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_VIDEO_EXTENSIONS),
        "Videos",
        "No hay videos en storage/input/",
        extensions=SUPPORTED_VIDEO_EXTENSIONS,
    )
    if archivo_path is None:
        return

    subtitulo_path = resolve_input_file(subtitulo)
    carpeta_salida = settings.OUTPUT_DIR / "marcas_agua"
    carpeta_salida.mkdir(exist_ok=True)
    out_path = carpeta_salida / f"{archivo_path.stem}_subtitulado{archivo_path.suffix}"

    try:
        FFmpegTool().burn_subtitles(archivo_path, subtitulo_path, out_path)
        console.print(f"✨ [bold green]Video subtitulado en:[/bold green] storage/output/marcas_agua/{out_path.name}")
        notify("Subtítulos Incrustados", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la incrustación de subtítulos de {archivo_path.name}")


# ---------------------------------------------------------
# 13. QUITAR FONDO DE IMÁGENES (rembg)
# ---------------------------------------------------------
@app.command(name="quitar-fondo", short_help="Elimina el fondo de una imagen automáticamente")
def quitar_fondo_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Imagen de origen"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Elimina el fondo de una imagen automáticamente usando rembg (modelo U2Net), dejándolo transparente."""
    from src.tools.rembg_tool import RembgTool

    archivo_path = select_single_file(
        archivo,
        get_available_files_by_exts(SUPPORTED_IMAGE_EXTENSIONS),
        "Imágenes",
        "No hay imágenes en storage/input/",
        extensions=SUPPORTED_IMAGE_EXTENSIONS,
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "sin_fondo"
    carpeta_salida.mkdir(exist_ok=True)
    out_path = carpeta_salida / f"{archivo_path.stem}.png"

    try:
        console.print("[bold cyan]✂️ Eliminando fondo con rembg (puede tardar la primera vez)...[/bold cyan]")
        RembgTool().remove_background(archivo_path, out_path)
        console.print(f"✨ [bold green]Imagen sin fondo en:[/bold green] storage/output/sin_fondo/{out_path.name}")
        notify("Fondo Eliminado", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"la eliminación de fondo de {archivo_path.name}")


# ---------------------------------------------------------
# 14. ESTADO DEL SISTEMA (tb estado)
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

    table.add_row("storage/input (Entrada)", str(in_count), f"{in_size / (1024 * 1024):.2f} MB")
    table.add_row("storage/output (Salida)", str(out_count), f"{out_size / (1024 * 1024):.2f} MB")
    console.print(table)

    # Estado de contenedores
    console.print("\n[bold cyan]🐳 Imágenes de Docker asociadas:[/bold cyan]")
    try:
        import subprocess

        res = subprocess.run(
            [
                "docker",
                "images",
                "--filter=reference=local/toolbox-calibre*",
                "--filter=reference=*ffmpeg*",
                "--filter=reference=*yt-dlp*",
                "--format",
                "{{.Repository}}:{{.Tag}}\t{{.Size}}",
            ],
            capture_output=True,
            text=True,
            timeout=3,
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


# ---------------------------------------------------------
# 10. INTERFAZ WEB (media web)
# ---------------------------------------------------------
@app.command(name="web", short_help="Inicia la interfaz gráfica web en el navegador")
def iniciar_web(
    ctx: typer.Context,
    port: int = typer.Option(8000, "--port", "-p", help="Puerto HTTP"),
    no_browser: bool = typer.Option(False, "--no-browser", help="No abrir automáticamente el navegador"),
    local: bool = typer.Option(False, "--local", help="Ejecutar servidor localmente sin contenedor Docker"),
):
    import webbrowser

    from src.core.docker_runner import is_docker_running

    url = f"http://localhost:{port}"

    console.print(
        Panel(
            f"[bold green]🚀 Iniciando MediaBox Web en [underline]{url}[/underline][/bold green]\n\n"
            "[dim]Presiona Ctrl+C para detener el servidor.[/dim]",
            title="[bold cyan]MediaBox UI[/bold cyan]",
            border_style="#6366f1",
        )
    )

    if not no_browser:
        webbrowser.open(url)

    if not local and is_docker_running():
        import subprocess

        cmd = [
            "docker",
            "compose",
            "-f",
            str(settings.DOCKER_COMPOSE_FILE),
            "up",
            "web",
        ]
        try:
            subprocess.run(cmd, cwd=str(settings.BASE_DIR))
        except KeyboardInterrupt:
            console.print("\n[yellow]Deteniendo servicio web de Docker...[/yellow]")
            subprocess.run(
                ["docker", "compose", "-f", str(settings.DOCKER_COMPOSE_FILE), "stop", "web"],
                cwd=str(settings.BASE_DIR),
            )
    else:
        try:
            import uvicorn

            # nosec B104 -- modo --local explícito: el usuario elige exponerlo en su propia red;
            # el modo Docker (default) publica el puerto solo en 127.0.0.1 (ver docker-compose.yml).
            uvicorn.run("src.web.app:app", host="0.0.0.0", port=port, log_level="info")  # nosec B104
        except ImportError:
            console.print(
                "[red]Para ejecutar en modo local sin Docker, instala uvicorn y fastapi: pip install -e '.[web]'[/red]"
            )


@app.command(name="velocidad", short_help="Ajusta la velocidad de reproducción de un audio/video sin alterar el tono")
def velocidad_audio_cli(
    ctx: typer.Context,
    archivo: Optional[str] = typer.Argument(None, help="Archivo de audio o video"),
    velocidad: float = typer.Option(1.5, "--velocidad", "-v", help="Multiplicador de velocidad (ej. 0.75, 1.25, 1.5, 2.0)"),
    salida: Optional[str] = typer.Option(None, "--salida", "-s", help="Nombre del archivo resultante"),
    open_folder: bool = typer.Option(False, "--open", "-o", help="Abre la carpeta de salida al finalizar"),
):
    """Modifica la velocidad de reproducción de audio usando FFmpeg atempo."""
    disponibles = sorted(list(settings.INPUT_DIR.rglob("*.mp3")) + list(settings.INPUT_DIR.rglob("*.wav")) + list(settings.INPUT_DIR.rglob("*.mp4")))
    archivo_path = select_single_file(
        archivo, disponibles, "Audios / Videos", "No hay archivos de audio/video en storage/input/."
    )
    if archivo_path is None:
        return

    carpeta_salida = settings.OUTPUT_DIR / "audios"
    carpeta_salida.mkdir(exist_ok=True)
    out_name = salida if salida else f"{archivo_path.stem}_{velocidad}x.mp3"
    if not out_name.endswith(".mp3"):
        out_name += ".mp3"
    out_path = carpeta_salida / out_name

    try:
        console.print(f"[bold cyan]⚡ Ajustando velocidad a {velocidad}x con FFmpeg...[/bold cyan]")
        FFmpegTool().change_speed(archivo_path, out_path, velocidad=velocidad)
        console.print(f"✨ [bold green]Audio con velocidad modificada en:[/bold green] storage/output/audios/{out_path.name}")
        notify("Velocidad Modificada", out_path.name)
        if open_folder:
            open_directory(carpeta_salida)
    except Exception as e:
        handle_execution_error(e, ctx, f"el cambio de velocidad de {archivo_path.name}")


@app.command(name="biblioteca", short_help="Muestra el catálogo de archivos procesados y listos")
@app.command(name="historial", hidden=True)
def biblioteca_cli():
    """Muestra una lista organizada de todos los archivos generados en storage/output/."""
    table = Table(title="📂 Biblioteca de Archivos Procesados (storage/output/)")
    table.add_column("Categoría", style="cyan")
    table.add_column("Archivo", style="bold white")
    table.add_column("Tamaño", style="green")
    table.add_column("Fecha", style="dim")

    count = 0
    for cat_dir in sorted(settings.OUTPUT_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        for f in sorted(cat_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not f.is_file() or f.name.startswith("."):
                continue
            count += 1
            size_mb = f.stat().st_size / (1024 * 1024)
            size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{(f.stat().st_size / 1024):.1f} KB"
            mtime_str = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            table.add_row(cat_dir.name, f.name, size_str, mtime_str)

    if count == 0:
        return console.print("[yellow]La biblioteca está vacía. Procesa tus primeros archivos con el toolbox.[/yellow]")
    console.print(table)
    console.print(f"Total: [bold green]{count}[/bold green] archivos disponibles.")


@app.command(name="limpiar-temp", short_help="Limpia archivos temporales y subidas huérfanas en storage/input")
def limpiar_temp_cli():
    """Purga carpetas temporales para recuperar espacio en disco."""
    deleted = 0
    freed_bytes = 0
    for folder in [settings.INPUT_DIR / "temp", settings.INPUT_DIR / "uploads", settings.STORAGE_DIR / "temp"]:
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    try:
                        freed_bytes += f.stat().st_size
                        f.unlink()
                        deleted += 1
                    except Exception:
                        pass

    freed_mb = freed_bytes / (1024 * 1024)
    console.print(f"🧹 [bold green]Limpieza de caché completada:[/bold green] {deleted} archivos temporales eliminados ({freed_mb:.2f} MB liberados).")


app.command(name="vaciar-cache", short_help="Alias de 'limpiar-temp' (Vacía archivos temporales y caché)")(limpiar_temp_cli)


@app.command(name="purgar", short_help="Vacía todos los archivos en input y output conservando las carpetas")
def purgar_storage_cli(
    si: bool = typer.Option(False, "--si", "-y", help="Confirma el vaciado sin pedir confirmación interactiva"),
):
    """
    Vacía todo el almacenamiento (archivos subidos y generados) recuperando espacio en disco.
    Conserva siempre intactas las carpetas clasificatorias por defecto y sus .gitkeep.
    """
    from src.core.storage import purge_storage

    if not si:
        confirm = typer.confirm("¿Estás seguro de que deseas vaciar TODO el almacenamiento (input y output)? (Las carpetas se conservarán)")
        if not confirm:
            console.print("[yellow]Operación cancelada.[/yellow]")
            return

    res = purge_storage(target="all")
    console.print(
        f"🧹 [bold green]Almacenamiento vaciado:[/bold green] Se eliminaron [bold]{res['deleted_count']}[/bold] archivos ({res['freed_human']} liberados). Las carpetas clasificatorias se mantienen intactas."
    )


if __name__ == "__main__":
    app()
