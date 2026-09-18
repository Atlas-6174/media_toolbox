import mimetypes
import os
import shutil
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.docker_runner import is_docker_running
from src.core.logging_config import setup_logging
from src.core.storage import ensure_default_directories
from src.tools.calibre import CalibreTool
from src.tools.cmyk import CmykTool
from src.tools.compressor import VideoCompressorTool
from src.tools.downloader import DownloaderTool
from src.tools.ffmpeg import FFmpegTool
from src.tools.gif import GifTool
from src.tools.image import ImageTool
from src.tools.markdown_tool import MarkdownTool
from src.tools.office import SUPPORTED_OFFICE_EXTENSIONS, OfficeTool
from src.tools.pdf import PdfTool
from src.tools.privacy import PrivacyTool
from src.tools.rembg_tool import RembgTool
from src.tools.trimmer import TrimmerTool
from src.web.cleanup import cleanup_old_files

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Garantizar carpetas clasificatorias por defecto con .gitkeep
    ensure_default_directories()
    # Limpieza inicial de archivos huérfanos con más de 2 horas
    cleanup_old_files(7200)
    logger.info("MediaBox web iniciado (logs también en storage/logs/web.log)")
    yield
    logger.info("MediaBox web detenido")


app = FastAPI(
    title="MediaBox Web",
    description="Interfaz gráfica moderna para Media Toolbox",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_unhandled_exceptions(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Error no manejado en %s %s", request.method, request.url.path)
        raise


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Estado de tareas y lotes en memoria
tasks: Dict[str, dict] = {}
batches: Dict[str, dict] = {}
_task_created_at: Dict[str, float] = {}
_batch_created_at: Dict[str, float] = {}
TASK_TTL_SECONDS = 6 * 3600  # las tareas/lotes en memoria expiran tras 6 horas


def _prune_expired(store: Dict[str, dict], timestamps: Dict[str, float]) -> None:
    """Purga entradas de tareas/lotes en memoria más antiguas que TASK_TTL_SECONDS."""
    now = time.time()
    expired = [key for key, created_at in timestamps.items() if now - created_at > TASK_TTL_SECONDS]
    for key in expired:
        store.pop(key, None)
        timestamps.pop(key, None)


def new_task_id() -> str:
    _prune_expired(tasks, _task_created_at)
    task_id = str(uuid.uuid4())
    _task_created_at[task_id] = time.time()
    return task_id


def new_batch_id() -> str:
    _prune_expired(batches, _batch_created_at)
    batch_id = str(uuid.uuid4())
    _batch_created_at[batch_id] = time.time()
    return batch_id


def mark_task_error(task_id: str, exc: Exception) -> None:
    """Registra la excepción en el logger (consola + storage/logs/web.log) y marca la tarea como fallida."""
    logger.exception("La tarea %s terminó con error", task_id)
    tasks[task_id] = {"status": "error", "message": str(exc)}


def safe_filename(name: Optional[str]) -> str:
    """Reduce un nombre de archivo a su componente base, sin rutas ni segmentos '.'/'..' (previene path traversal)."""
    candidate = Path((name or "").strip()).name
    if not candidate or candidate in (".", ".."):
        candidate = f"archivo_{uuid.uuid4().hex[:8]}"
    return candidate


def save_upload(file: UploadFile, dest_dir: Path) -> Path:
    """Guarda un UploadFile dentro de dest_dir usando un nombre saneado."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_filename(file.filename)
    with open(dest_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    return dest_path


def resolve_safe_path(base_dir: Path, *parts: str) -> Path:
    """Construye una ruta bajo base_dir saneando cada segmento y confirmando que el resultado no escapa de base_dir."""
    base_resolved = base_dir.resolve()
    candidate = base_resolved
    for part in parts:
        candidate = candidate / safe_filename(part)
    candidate = candidate.resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise HTTPException(status_code=400, detail="Ruta de archivo inválida")
    return candidate


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>MediaBox UI no encontrada. Revisa src/web/static/index.html</h1>"


@app.get("/api/status")
async def get_status():
    docker_ok = is_docker_running()

    def dir_info(path: Path):
        count = 0
        size = 0
        if path.exists():
            for p in path.rglob("*"):
                if p.is_file() and p.name != ".gitkeep" and p.name != ".DS_Store":
                    count += 1
                    size += p.stat().st_size
        return count, round(size / (1024 * 1024), 2)

    in_count, in_size = dir_info(settings.INPUT_DIR)
    out_count, out_size = dir_info(settings.OUTPUT_DIR)

    return {
        "docker": docker_ok,
        "storage": {
            "input": {"count": in_count, "size_mb": in_size},
            "output": {"count": out_count, "size_mb": out_size},
        },
    }


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return tasks[task_id]


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    dest_dir = settings.INPUT_DIR / "uploads"
    file_path = save_upload(file, dest_dir)

    return {"filename": file_path.name, "path": str(file_path), "size_kb": round(file_path.stat().st_size / 1024, 2)}


@app.post("/api/convert")
async def convert_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pagina: str = Form("a4"),
    perfil: Optional[str] = Form(None),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "books"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}.pdf"
    tasks[task_id] = {"status": "running", "progress": 10, "message": "Iniciando conversión..."}

    def run():
        try:
            tasks[task_id]["progress"] = 30
            tasks[task_id]["message"] = "Procesando documento con Calibre..."
            CalibreTool().convert(input_path, output_path, paper_size=pagina, output_profile=perfil)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Conversión completada",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/audio")
async def extract_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    formato: str = Form("mp3"),
    normalizar: bool = Form(False),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "audios"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    fmt = formato.lstrip(".").lower()
    output_path = out_dir / f"{input_path.stem}.{fmt}"
    tasks[task_id] = {"status": "running", "progress": 15, "message": "Extrayendo pista de audio..."}

    def run():
        try:
            FFmpegTool().convert(input_path, output_path, normalizar=normalizar)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Audio extraído exitosamente",
                "download_url": f"/api/files/audios/{output_path.name}",
                "preview_url": f"/api/preview/audios/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/download")
async def download_media(
    background_tasks: BackgroundTasks, url: str = Form(...), audio: bool = Form(False), calidad: str = Form("max")
):
    task_id = new_task_id()
    tasks[task_id] = {"status": "running", "progress": 10, "message": "Conectando y analizando enlace..."}

    def run():
        try:
            tasks[task_id]["progress"] = 30
            tasks[task_id]["message"] = "Descargando medio..."
            DownloaderTool().descargar(url, solo_audio=audio, calidad=calidad)

            sub = "audios" if audio else "videos"
            target_dir = settings.INPUT_DIR / sub
            latest_file = max(target_dir.glob("*.*"), key=os.path.getctime, default=None)

            fname = latest_file.name if latest_file else "descarga"
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Descarga completada",
                "download_url": f"/api/input-files/{sub}/{fname}",
                "filename": fname,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/trim")
async def trim_media(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    desde: str = Form("00:00:00"),
    hasta: Optional[str] = Form(None),
    duracion: Optional[str] = Form(None),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "recortes"
    out_dir = settings.OUTPUT_DIR / "recortes"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_corte{input_path.suffix}"
    tasks[task_id] = {"status": "running", "progress": 20, "message": "Recortando clip sin pérdida de calidad..."}

    def run():
        try:
            TrimmerTool().trim(input_path, output_path, desde=desde, hasta=hasta, duracion=duracion)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Recorte finalizado",
                "download_url": f"/api/files/recortes/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/gif")
async def create_gif(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    desde: str = Form("00:00:00"),
    duracion: str = Form("5s"),
    fps: int = Form(15),
    ancho: int = Form(480),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "gifs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}.gif"
    tasks[task_id] = {"status": "running", "progress": 25, "message": "Generando paleta y renderizando GIF..."}

    def run():
        try:
            GifTool().create_gif(input_path, output_path, desde=desde, duracion=duracion, fps=fps, ancho=ancho)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "GIF generado exitosamente",
                "download_url": f"/api/files/gifs/{output_path.name}",
                "preview_url": f"/api/preview/gifs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/compress")
async def compress_video(
    background_tasks: BackgroundTasks, file: UploadFile = File(...), perfil: str = Form("equilibrada")
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "comprimidos"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_comprimido.mp4"
    tasks[task_id] = {"status": "running", "progress": 20, "message": f"Comprimiendo video con perfil {perfil}..."}

    def run():
        try:
            VideoCompressorTool().compress(input_path, output_path, perfil=perfil)
            orig_size = input_path.stat().st_size / (1024 * 1024)
            new_size = output_path.stat().st_size / (1024 * 1024)
            ahorro = round((1 - (new_size / orig_size)) * 100, 1) if orig_size > 0 else 0
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": f"Compresión finalizada. Reducción de tamaño: {ahorro}% ({orig_size:.1f}MB -> {new_size:.1f}MB)",
                "download_url": f"/api/files/comprimidos/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/mute")
async def mute_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "silenciados"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_mute{input_path.suffix}"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Eliminando pista de audio..."}

    def run():
        try:
            FFmpegTool().mute(input_path, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Video silenciado con éxito",
                "download_url": f"/api/files/silenciados/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/snapshot")
async def capture_snapshot(
    background_tasks: BackgroundTasks, file: UploadFile = File(...), tiempo: str = Form("00:00:01")
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "capturas"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_captura.jpg"
    tasks[task_id] = {"status": "running", "progress": 30, "message": f"Extrayendo fotograma en {tiempo}..."}

    def run():
        try:
            FFmpegTool().snapshot(input_path, output_path, tiempo=tiempo)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Fotograma capturado",
                "download_url": f"/api/files/capturas/{output_path.name}",
                "preview_url": f"/api/preview/capturas/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/image")
async def convert_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    formato: str = Form("webp"),
    calidad: int = Form(80),
    ancho: Optional[int] = Form(None),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "imagenes"
    out_dir = settings.OUTPUT_DIR / "imagenes"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    fmt = formato.lstrip(".").lower()
    output_path = out_dir / f"{input_path.stem}.{fmt}"
    tasks[task_id] = {"status": "running", "progress": 30, "message": f"Optimizando imagen a {fmt.upper()}..."}

    def run():
        try:
            ImageTool().convert(input_path, output_path, calidad=calidad, ancho=ancho)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Imagen procesada",
                "download_url": f"/api/files/imagenes/{output_path.name}",
                "preview_url": f"/api/preview/imagenes/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/merge")
async def merge_pdfs(
    background_tasks: BackgroundTasks, files: List[UploadFile] = File(...), salida: str = Form("documento_unido.pdf")
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_paths = [save_upload(f, in_dir) for f in files]

    out_name = salida if salida.endswith(".pdf") else f"{salida}.pdf"
    output_path = out_dir / out_name
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Uniendo documentos PDF con Poppler..."}

    def run():
        try:
            PdfTool().unir(input_paths, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": f"Se unieron {len(input_paths)} PDFs con éxito",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/compress")
async def compress_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    perfil: str = Form("ebook"),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdf_comprimidos"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_comprimido.pdf"
    tasks[task_id] = {"status": "running", "progress": 20, "message": "Iniciando compresión de PDF..."}

    def run():
        try:
            tasks[task_id]["progress"] = 50
            tasks[task_id]["message"] = f"Comprimiendo PDF con Ghostscript (perfil: {perfil})..."
            stats = PdfTool().compress(input_path, output_path, perfil=perfil)

            in_mb = stats["input_size"] / (1024 * 1024)
            out_mb = stats["output_size"] / (1024 * 1024)
            if stats.get("was_already_optimal"):
                msg = f"El PDF ya estaba en su tamaño óptimo ({in_mb:.1f} MB)"
            else:
                msg = f"PDF comprimido un {stats['saved_pct']}% ({in_mb:.1f} MB → {out_mb:.1f} MB)"

            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": msg,
                "download_url": f"/api/files/pdf_comprimidos/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/privacy/inspect")
async def inspect_privacy_metadata(file: UploadFile = File(...)):
    in_dir = settings.INPUT_DIR / "temp"
    in_dir.mkdir(parents=True, exist_ok=True)
    temp_path = in_dir / f"inspect_{uuid.uuid4().hex[:8]}_{safe_filename(file.filename)}"
    with open(temp_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    try:
        metadata = PrivacyTool().inspect(temp_path)
        return {"filename": file.filename, "metadata": metadata}
    except Exception as e:
        logger.exception("Falló la inspección de metadatos de %s", file.filename)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.post("/api/privacy/clean")
async def clean_privacy_metadata(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "uploads"
    out_dir = settings.OUTPUT_DIR / "limpios"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"limpio_{input_path.name}"
    tasks[task_id] = {"status": "running", "progress": 20, "message": "Iniciando limpieza de metadatos con MAT2..."}

    def run():
        try:
            tasks[task_id]["progress"] = 50
            tasks[task_id]["message"] = "Eliminando metadatos y rastros de privacidad..."
            PrivacyTool().clean(input_path, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Metadatos eliminados con éxito (Archivo 100% limpio)",
                "download_url": f"/api/files/limpios/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/download/inspect")
async def inspect_download_url(url: str = Form(...)):
    try:
        info = DownloaderTool().inspect(url)
        return info
    except Exception as e:
        return {"title": url, "thumbnail": None, "error": str(e)}


@app.post("/api/cmyk/convert")
async def convert_to_cmyk(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    formato: str = Form("pdf"),
    perfil: str = Form("fogra39"),
    dpi: int = Form(300),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "cmyk"
    out_dir = settings.OUTPUT_DIR / "cmyk"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    fmt = formato.lstrip(".").lower()
    ext_out = "pdf" if fmt == "pdf" else ("tif" if fmt in ["tiff", "tif"] else "jpg")
    output_path = out_dir / f"{input_path.stem}_cmyk.{ext_out}"
    tasks[task_id] = {"status": "running", "progress": 20, "message": "Iniciando preparación para imprenta..."}

    def run():
        try:
            tasks[task_id]["progress"] = 40
            tasks[task_id]["message"] = "Procesando vectores y convirtiendo a CMYK..."
            CmykTool().convert(input_path, output_path, formato=fmt, perfil=perfil, dpi=dpi)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": f"Archivo convertido a CMYK con éxito ({fmt.upper()})",
                "download_url": f"/api/files/cmyk/{output_path.name}",
                "filename": output_path.name,
                "preview_url": f"/api/preview/cmyk/{output_path.name}" if fmt in ["jpg", "jpeg"] else None,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.get("/api/files/{subfolder}/{filename}")
async def download_output_file(subfolder: str, filename: str):
    file_path = resolve_safe_path(settings.OUTPUT_DIR, subfolder, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path=str(file_path), filename=file_path.name, media_type=media_type)


@app.get("/api/input-files/{subfolder}/{filename}")
async def download_input_file(subfolder: str, filename: str):
    file_path = resolve_safe_path(settings.INPUT_DIR, subfolder, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path=str(file_path), filename=filename, media_type=media_type)


@app.get("/api/preview/{subfolder}/{filename}")
async def preview_output_file(subfolder: str, filename: str):
    """Sirve un archivo de storage/output para previsualización inline (audio, imagen, texto)
    en lugar de forzar su descarga, para usarlo como src en <audio>/<img> o abrirlo en pestaña."""
    file_path = resolve_safe_path(settings.OUTPUT_DIR, subfolder, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
        content_disposition_type="inline",
    )


@app.post("/api/batch/convert")
async def batch_convert(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    tipo: str = Form(...),
    formato: Optional[str] = Form(None),
    perfil: Optional[str] = Form(None),
    normalizar: bool = Form(False),
    calidad: Optional[int] = Form(80),
):
    if not files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos")

    batch_id = new_batch_id()
    batches[batch_id] = {
        "id": batch_id,
        "status": "running",
        "tipo": tipo,
        "total": len(files),
        "completed": 0,
        "failed": 0,
        "output_files": [],
        "zip_path": None,
    }

    file_records = []
    for f in files:
        if tipo in ["audio", "compress"]:
            sub = "videos"
        elif tipo in ["pdf_compress"]:
            sub = "pdfs"
        elif tipo in ["privacy"]:
            sub = "uploads"
        elif tipo in ["cmyk"]:
            sub = "cmyk"
        else:
            sub = "imagenes"
        in_dir = settings.INPUT_DIR / sub
        in_path = save_upload(f, in_dir)
        file_records.append((in_path.name, in_path))

    def run_batch():
        out_files = []
        for _, in_path in file_records:
            try:
                if tipo == "audio":
                    fmt = (formato or "mp3").lstrip(".").lower()
                    out_dir = settings.OUTPUT_DIR / "audios"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{in_path.stem}.{fmt}"
                    FFmpegTool().convert(in_path, out_path, normalizar=normalizar)
                    out_files.append(out_path)
                elif tipo == "compress":
                    prf = perfil or "equilibrada"
                    out_dir = settings.OUTPUT_DIR / "comprimidos"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{in_path.stem}_comprimido.mp4"
                    VideoCompressorTool().compress(in_path, out_path, perfil=prf)
                    out_files.append(out_path)
                elif tipo == "image":
                    fmt = (formato or "webp").lstrip(".").lower()
                    out_dir = settings.OUTPUT_DIR / "imagenes"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{in_path.stem}.{fmt}"
                    ImageTool().convert(in_path, out_path, calidad=calidad or 80)
                    out_files.append(out_path)
                elif tipo == "privacy":
                    out_dir = settings.OUTPUT_DIR / "limpios"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"limpio_{in_path.name}"
                    PrivacyTool().clean(in_path, out_path)
                    out_files.append(out_path)
                elif tipo == "pdf_compress":
                    prf = perfil or "ebook"
                    out_dir = settings.OUTPUT_DIR / "pdf_comprimidos"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{in_path.stem}_comprimido.pdf"
                    PdfTool().compress(in_path, out_path, perfil=prf)
                    out_files.append(out_path)
                elif tipo == "cmyk":
                    fmt = (formato or "pdf").lstrip(".").lower()
                    ext_out = "pdf" if fmt == "pdf" else ("tif" if fmt in ["tiff", "tif"] else "jpg")
                    out_dir = settings.OUTPUT_DIR / "cmyk"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{in_path.stem}_cmyk.{ext_out}"
                    CmykTool().convert(in_path, out_path, formato=fmt, perfil=perfil or "fogra39", dpi=300)
                    out_files.append(out_path)
                batches[batch_id]["completed"] += 1
            except Exception:
                logger.exception("Falló %s en el lote %s", in_path.name, batch_id)
                batches[batch_id]["failed"] += 1
                batches[batch_id]["completed"] += 1

        zip_dir = settings.OUTPUT_DIR / "zips"
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"mediabox_lote_{batch_id[:8]}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for op in out_files:
                if op.exists():
                    zf.write(op, arcname=op.name)

        batches[batch_id]["output_files"] = [str(p) for p in out_files]
        batches[batch_id]["zip_path"] = str(zip_path)
        batches[batch_id]["status"] = "done"
        batches[batch_id]["download_zip"] = f"/api/batch/download/{batch_id}"

    background_tasks.add_task(run_batch)
    return {"batch_id": batch_id, "total": len(files)}


@app.get("/api/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    if batch_id not in batches:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    b = batches[batch_id]
    total = b["total"]
    done_count = b["completed"] + b["failed"]
    percent = int((done_count / total) * 100) if total > 0 else 100
    return {
        "id": batch_id,
        "status": b["status"],
        "total": total,
        "completed": b["completed"],
        "failed": b["failed"],
        "percent": percent,
        "download_zip": b.get("download_zip"),
    }


@app.get("/api/batch/download/{batch_id}")
async def download_batch_zip(batch_id: str):
    if batch_id not in batches or not batches[batch_id].get("zip_path"):
        raise HTTPException(status_code=404, detail="Lote o ZIP no encontrado")
    zip_path = Path(batches[batch_id]["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Archivo ZIP no existe")
    return FileResponse(path=str(zip_path), filename=zip_path.name, media_type="application/zip")


@app.post("/api/cleanup")
async def trigger_cleanup():
    deleted = cleanup_old_files(3600)
    return {"deleted_files": deleted}


def format_size(bytes_num: int) -> str:
    val = float(bytes_num)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024
    return f"{val:.1f} TB"


def get_file_type(ext: str) -> str:
    ext = ext.lower()
    if ext in [".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"]:
        return "audio"
    elif ext in [".mp4", ".mkv", ".mov", ".webm", ".avi"]:
        return "video"
    elif ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff", ".svg"]:
        return "image"
    elif ext == ".pdf":
        return "pdf"
    elif ext == ".zip":
        return "archive"
    return "other"


def get_dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.name.startswith("."))


@app.get("/api/library")
async def list_library():
    """Lista todos los archivos procesados en storage/output ordenados por fecha descendente."""
    items = []
    output_dir = settings.OUTPUT_DIR
    if not output_dir.exists():
        return {"items": [], "total": 0}

    for category_dir in output_dir.iterdir():
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for file_path in category_dir.iterdir():
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            stat = file_path.stat()
            ext = file_path.suffix.lower()
            ftype = get_file_type(ext)
            preview_url = f"/api/preview/{category}/{file_path.name}" if ftype in ["audio", "image"] else None
            items.append({
                "filename": file_path.name,
                "category": category,
                "size_bytes": stat.st_size,
                "size_human": format_size(stat.st_size),
                "mtime": stat.st_mtime,
                "mtime_human": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
                "type": ftype,
                "download_url": f"/api/files/{category}/{file_path.name}",
                "preview_url": preview_url,
            })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"items": items, "total": len(items)}


@app.delete("/api/library/{category}/{filename}")
async def delete_library_file(category: str, filename: str):
    """Elimina un archivo del almacenamiento de salida."""
    target = resolve_safe_path(settings.OUTPUT_DIR, category, filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    try:
        target.unlink()
        return {"status": "deleted", "filename": target.name}
    except Exception as e:
        logger.exception("Falló al borrar %s", target)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/storage/info")
async def storage_info():
    """Métricas en tiempo real del uso de disco en storage."""
    in_bytes = get_dir_size(settings.INPUT_DIR)
    out_bytes = get_dir_size(settings.OUTPUT_DIR)
    temp_bytes = get_dir_size(settings.INPUT_DIR / "temp") + get_dir_size(settings.INPUT_DIR / "uploads")
    out_files = sum(1 for f in settings.OUTPUT_DIR.rglob("*") if f.is_file() and not f.name.startswith("."))

    return {
        "input_bytes": in_bytes,
        "input_human": format_size(in_bytes),
        "output_bytes": out_bytes,
        "output_human": format_size(out_bytes),
        "temp_bytes": temp_bytes,
        "temp_human": format_size(temp_bytes),
        "output_files_count": out_files,
    }


@app.post("/api/storage/clean-temp")
async def clean_temp_storage():
    """Limpia archivos temporales y cargas acumuladas en storage/input y storage/temp."""
    deleted = 0
    freed_bytes = 0
    folders_to_clean = [
        settings.INPUT_DIR / "temp",
        settings.INPUT_DIR / "uploads",
        settings.STORAGE_DIR / "temp",
    ]
    for folder in folders_to_clean:
        if folder.exists():
            for f in folder.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    try:
                        freed_bytes += f.stat().st_size
                        f.unlink()
                        deleted += 1
                    except Exception:
                        pass
                elif f.is_dir() and not f.name.startswith("."):
                    try:
                        shutil.rmtree(f, ignore_errors=True)
                        deleted += 1
                    except Exception:
                        pass
    return {
        "deleted_count": deleted,
        "freed_bytes": freed_bytes,
        "freed_human": format_size(freed_bytes),
    }


@app.post("/api/storage/purge")
async def purge_storage_endpoint(target: str = Query("all", pattern="^(all|input|output)$")):
    """Purga archivos de entrada y/o salida conservando las carpetas clasificatorias y .gitkeep."""
    from src.core.storage import purge_storage
    return purge_storage(target=target)


@app.post("/api/pdf/ocr")
async def ocr_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    idioma: str = Form("spa+eng"),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_ocr.pdf"
    tasks[task_id] = {"status": "running", "progress": 20, "message": "Iniciando OCR con Tesseract..."}

    def run():
        try:
            tasks[task_id]["progress"] = 50
            tasks[task_id]["message"] = f"Reconociendo texto en PDF ({idioma})..."
            PdfTool().ocr(input_path, output_path, idioma=idioma)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Capa OCR de texto añadida con éxito",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/extract-pages")
async def extract_pdf_pages(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    paginas: str = Form("1"),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    clean_pages = paginas.replace(" ", "")
    output_path = out_dir / f"{input_path.stem}_paginas_{clean_pages}.pdf"
    tasks[task_id] = {"status": "running", "progress": 30, "message": f"Extrayendo páginas {paginas}..."}

    def run():
        try:
            PdfTool().extract_pages(input_path, output_path, paginas=clean_pages)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": f"Páginas {paginas} extraídas con éxito",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/to-images")
async def pdf_to_images_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    formato: str = Form("png"),
    dpi: int = Form(300),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    input_path = save_upload(file, in_dir)

    temp_img_dir = settings.INPUT_DIR / "temp" / f"pdf_imgs_{uuid.uuid4().hex[:8]}"
    temp_img_dir.mkdir(parents=True, exist_ok=True)

    out_zip_dir = settings.OUTPUT_DIR / "zips"
    out_zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_zip_dir / f"{input_path.stem}_imagenes_{formato}.zip"

    tasks[task_id] = {"status": "running", "progress": 25, "message": f"Renderizando páginas a {formato.upper()} ({dpi} DPI)..."}

    def run():
        try:
            images = PdfTool().pdf_to_images(input_path, temp_img_dir, formato=formato, dpi=dpi)
            if not images:
                raise RuntimeError("No se generaron imágenes del PDF.")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for img in images:
                    zf.write(img, arcname=img.name)
            shutil.rmtree(temp_img_dir, ignore_errors=True)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": f"{len(images)} páginas convertidas a imágenes con éxito",
                "download_url": f"/api/files/zips/{zip_path.name}",
                "filename": zip_path.name,
            }
        except Exception as e:
            shutil.rmtree(temp_img_dir, ignore_errors=True)
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/audio/speed")
async def audio_speed_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    velocidad: float = Form(1.5),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "audios"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)

    output_path = out_dir / f"{input_path.stem}_{velocidad}x.mp3"
    tasks[task_id] = {"status": "running", "progress": 30, "message": f"Ajustando velocidad a {velocidad}x con FFmpeg..."}

    def run():
        try:
            FFmpegTool().change_speed(input_path, output_path, velocidad=velocidad)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": f"Audio procesado a {velocidad}x con éxito",
                "download_url": f"/api/files/audios/{output_path.name}",
                "filename": output_path.name,
                "preview_url": f"/api/preview/audios/{output_path.name}",
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


# ---------------------------------------------------------------------------
# MARKDOWN CONVERSION
# ---------------------------------------------------------------------------

MARKDOWN_SUPPORTED_EXTS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".csv", ".epub", ".txt",
    ".zip", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
}


@app.post("/api/convert/markdown")
async def convert_to_markdown(
    file: UploadFile = File(...),
):
    """
    Convierte un documento al formato Markdown usando markitdown.
    Soporta: PDF, DOCX, PPTX, XLSX, HTML, CSV, EPUB, TXT, imágenes, ZIP.
    Retorna el texto Markdown generado inline para previsualización, y lo
    guarda en storage/output/markdown/ para descarga posterior.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo vacío.")

    ext = Path(file.filename).suffix.lower()
    if ext not in MARKDOWN_SUPPORTED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"Formato '{ext}' no soportado. Formatos válidos: {', '.join(sorted(MARKDOWN_SUPPORTED_EXTS))}",
        )

    in_dir = settings.INPUT_DIR / "docs"
    out_dir = settings.OUTPUT_DIR / "markdown"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    output_path = out_dir / f"{input_path.stem}.md"

    try:
        tool = MarkdownTool()
        result_path = tool.convert(input_path, output_path)
        markdown_text = result_path.read_text(encoding="utf-8")
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "status": "done",
        "filename": output_path.name,
        "source_file": file.filename,
        "char_count": len(markdown_text),
        "line_count": markdown_text.count("\n") + 1,
        "markdown": markdown_text,
        "download_url": f"/api/files/markdown/{output_path.name}",
        "preview_url": f"/api/preview/markdown/{output_path.name}",
    }


@app.post("/api/convert/markdown/url")
async def convert_url_to_markdown(url: str = Form(...)):
    """
    Convierte el contenido de una URL pública a formato Markdown.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="La URL debe comenzar con http:// o https://")

    out_dir = settings.OUTPUT_DIR / "markdown"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generar nombre de archivo desde la URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.netloc.replace(".", "_").replace(":", "_")
    output_path = out_dir / f"{hostname}.md"

    try:
        tool = MarkdownTool()
        result_path = tool.convert_url(url, output_path)
        markdown_text = result_path.read_text(encoding="utf-8")
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "status": "done",
        "filename": output_path.name,
        "source_url": url,
        "char_count": len(markdown_text),
        "line_count": markdown_text.count("\n") + 1,
        "markdown": markdown_text,
        "download_url": f"/api/files/markdown/{output_path.name}",
        "preview_url": f"/api/preview/markdown/{output_path.name}",
    }


# ---------------------------------------------------------------------------
# PDF: ROTAR / PROTEGER / DESDE OFICINA
# ---------------------------------------------------------------------------


@app.post("/api/pdf/rotate")
async def rotate_pdf_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    angulo: int = Form(90),
    paginas: str = Form("1-z"),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    output_path = out_dir / f"{input_path.stem}_rotado.pdf"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Rotando páginas del PDF..."}

    def run():
        try:
            PdfTool().rotate(input_path, output_path, angulo=angulo, paginas=paginas)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "PDF rotado con éxito",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/protect")
async def protect_pdf_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    password: str = Form(...),
    password_propietario: Optional[str] = Form(None),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    output_path = out_dir / f"{input_path.stem}_protegido.pdf"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Cifrando PDF con AES-256..."}

    def run():
        try:
            PdfTool().protect(input_path, output_path, password_usuario=password, password_propietario=password_propietario)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "PDF protegido con éxito",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/from-office")
async def office_to_pdf_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() not in SUPPORTED_OFFICE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Formato no soportado. Formatos válidos: {', '.join(sorted(SUPPORTED_OFFICE_EXTENSIONS))}",
        )

    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "docs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    output_path = out_dir / f"{input_path.stem}.pdf"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Convirtiendo documento con LibreOffice..."}

    def run():
        try:
            OfficeTool().convert_to_pdf(input_path, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Documento convertido a PDF con éxito",
                "download_url": f"/api/files/pdfs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


# ---------------------------------------------------------------------------
# SUBTÍTULOS
# ---------------------------------------------------------------------------


@app.post("/api/subtitles/extract")
async def extract_subtitles_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pista: int = Form(0),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "subtitulos"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    output_path = out_dir / f"{input_path.stem}.srt"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Extrayendo pista de subtítulos..."}

    def run():
        try:
            FFmpegTool().extract_subtitles(input_path, output_path, pista=pista)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Subtítulos extraídos con éxito",
                "download_url": f"/api/files/subtitulos/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/subtitles/burn")
async def burn_subtitles_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subtitle_file: UploadFile = File(...),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "marcas_agua"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    subtitle_path = save_upload(subtitle_file, in_dir)
    output_path = out_dir / f"{input_path.stem}_subtitulado{input_path.suffix}"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Incrustando subtítulos en el video..."}

    def run():
        try:
            FFmpegTool().burn_subtitles(input_path, subtitle_path, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Subtítulos incrustados con éxito",
                "download_url": f"/api/files/marcas_agua/{output_path.name}",
                "preview_url": f"/api/preview/marcas_agua/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


# ---------------------------------------------------------------------------
# MARCA DE AGUA
# ---------------------------------------------------------------------------


@app.post("/api/watermark/image")
async def watermark_image_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    texto: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    posicion: str = Form("bottomright"),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "imagenes"
    out_dir = settings.OUTPUT_DIR / "marcas_agua"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    logo_path = save_upload(logo, in_dir) if logo is not None and logo.filename else None
    output_path = out_dir / f"{input_path.stem}_wm{input_path.suffix}"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Aplicando marca de agua..."}

    def run():
        try:
            ImageTool().watermark(input_path, output_path, texto=texto, logo_file=logo_path, posicion=posicion)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Marca de agua aplicada con éxito",
                "download_url": f"/api/files/marcas_agua/{output_path.name}",
                "preview_url": f"/api/preview/marcas_agua/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/watermark/video")
async def watermark_video_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    texto: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    posicion: str = Form("bottomright"),
):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "marcas_agua"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    logo_path = save_upload(logo, in_dir) if logo is not None and logo.filename else None
    output_path = out_dir / f"{input_path.stem}_wm{input_path.suffix}"
    tasks[task_id] = {"status": "running", "progress": 30, "message": "Aplicando marca de agua al video..."}

    def run():
        try:
            FFmpegTool().watermark(input_path, output_path, texto=texto, logo_file=logo_path, posicion=posicion)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Marca de agua aplicada con éxito",
                "download_url": f"/api/files/marcas_agua/{output_path.name}",
                "preview_url": f"/api/preview/marcas_agua/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}


# ---------------------------------------------------------------------------
# QUITAR FONDO DE IMÁGENES
# ---------------------------------------------------------------------------


@app.post("/api/image/remove-background")
async def remove_background_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    task_id = new_task_id()
    in_dir = settings.INPUT_DIR / "imagenes"
    out_dir = settings.OUTPUT_DIR / "sin_fondo"
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = save_upload(file, in_dir)
    output_path = out_dir / f"{input_path.stem}.png"
    tasks[task_id] = {"status": "running", "progress": 20, "message": "Eliminando fondo con rembg..."}

    def run():
        try:
            RembgTool().remove_background(input_path, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Fondo eliminado con éxito",
                "download_url": f"/api/files/sin_fondo/{output_path.name}",
                "preview_url": f"/api/preview/sin_fondo/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            mark_task_error(task_id, e)

    background_tasks.add_task(run)
    return {"task_id": task_id}
