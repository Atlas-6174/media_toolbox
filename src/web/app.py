import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.core.docker_runner import is_docker_running
from src.tools.calibre import CalibreTool
from src.tools.compressor import VideoCompressorTool
from src.tools.downloader import DownloaderTool
from src.tools.ffmpeg import FFmpegTool
from src.tools.gif import GifTool
from src.tools.image import ImageTool
from src.tools.pdf import PdfTool
from src.tools.trimmer import TrimmerTool
from src.web.cleanup import cleanup_old_files


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Limpieza inicial de archivos huérfanos con más de 2 horas
    cleanup_old_files(7200)
    yield


app = FastAPI(
    title="MediaBox Web",
    description="Interfaz gráfica moderna para Media Toolbox",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Estado de tareas en memoria
tasks: Dict[str, dict] = {}


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
    dest_dir.mkdir(parents=True, exist_ok=True)
    file_path = dest_dir / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"filename": file.filename, "path": str(file_path), "size_kb": round(file_path.stat().st_size / 1024, 2)}


@app.post("/api/convert")
async def convert_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pagina: str = Form("a4"),
    perfil: Optional[str] = Form(None),
):
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "books"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/audio")
async def extract_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...), formato: str = Form("mp3")):
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "audios"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    fmt = formato.lstrip(".").lower()
    output_path = out_dir / f"{input_path.stem}.{fmt}"
    tasks[task_id] = {"status": "running", "progress": 15, "message": "Extrayendo pista de audio..."}

    def run():
        try:
            FFmpegTool().convert(input_path, output_path)
            tasks[task_id] = {
                "status": "done",
                "progress": 100,
                "message": "Audio extraído exitosamente",
                "download_url": f"/api/files/audios/{output_path.name}",
                "preview_url": f"/api/files/audios/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/download")
async def download_media(
    background_tasks: BackgroundTasks, url: str = Form(...), audio: bool = Form(False), calidad: str = Form("max")
):
    task_id = str(uuid.uuid4())
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
            tasks[task_id] = {"status": "error", "message": str(e)}

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
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "recortes"
    out_dir = settings.OUTPUT_DIR / "recortes"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
            tasks[task_id] = {"status": "error", "message": str(e)}

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
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "gifs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
                "preview_url": f"/api/files/gifs/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/compress")
async def compress_video(
    background_tasks: BackgroundTasks, file: UploadFile = File(...), perfil: str = Form("equilibrada")
):
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "comprimidos"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/mute")
async def mute_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "silenciados"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/snapshot")
async def capture_snapshot(
    background_tasks: BackgroundTasks, file: UploadFile = File(...), tiempo: str = Form("00:00:01")
):
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "videos"
    out_dir = settings.OUTPUT_DIR / "capturas"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
                "preview_url": f"/api/files/capturas/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            tasks[task_id] = {"status": "error", "message": str(e)}

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
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "imagenes"
    out_dir = settings.OUTPUT_DIR / "imagenes"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = in_dir / file.filename
    with open(input_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

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
                "preview_url": f"/api/files/imagenes/{output_path.name}",
                "filename": output_path.name,
            }
        except Exception as e:
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.post("/api/pdf/merge")
async def merge_pdfs(
    background_tasks: BackgroundTasks, files: List[UploadFile] = File(...), salida: str = Form("documento_unido.pdf")
):
    task_id = str(uuid.uuid4())
    in_dir = settings.INPUT_DIR / "pdfs"
    out_dir = settings.OUTPUT_DIR / "pdfs"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_paths = []
    for f in files:
        fpath = in_dir / f.filename
        with open(fpath, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        input_paths.append(fpath)

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
            tasks[task_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(run)
    return {"task_id": task_id}


@app.get("/api/files/{subfolder}/{filename}")
async def download_output_file(subfolder: str, filename: str):
    file_path = settings.OUTPUT_DIR / subfolder / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")


@app.get("/api/input-files/{subfolder}/{filename}")
async def download_input_file(subfolder: str, filename: str):
    file_path = settings.INPUT_DIR / subfolder / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")


@app.post("/api/cleanup")
async def trigger_cleanup():
    deleted = cleanup_old_files(3600)
    return {"deleted_files": deleted}
