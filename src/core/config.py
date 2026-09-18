import os
import shutil
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings

SUPPORTED_BOOK_EXTENSIONS = [".epub", ".mobi", ".azw3", ".fb2", ".txt", ".docx", ".pdf"]
SUPPORTED_VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv"]
SUPPORTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic", ".heif", ".svg"]
SUPPORTED_DESIGN_EXTENSIONS = [".svg", ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".eps"]


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    INPUT_DIR: Path = STORAGE_DIR / "input"
    OUTPUT_DIR: Path = STORAGE_DIR / "output"
    DOCKER_COMPOSE_FILE: Path = BASE_DIR / "docker-compose.yml"

    UID: str = str(os.getuid() if hasattr(os, "getuid") else 1000)
    GID: str = str(os.getgid() if hasattr(os, "getgid") else 1000)


settings = Settings()
settings.INPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STANDARD_SUBDIRS = [
    "audios",
    "videos",
    "recortes",
    "comprimidos",
    "silenciados",
    "capturas",
    "gifs",
    "imagenes",
    "pdfs",
    "zips",
    "books",
    "limpios",
    "pdf_comprimidos",
    "cmyk",
    "markdown",
    "docs",
    "subtitulos",
    "marcas_agua",
    "sin_fondo",
]
for sub in STANDARD_SUBDIRS:
    (settings.INPUT_DIR / sub).mkdir(parents=True, exist_ok=True)
    (settings.OUTPUT_DIR / sub).mkdir(parents=True, exist_ok=True)


def resolve_input_file(path_or_name: str, allowed_extensions: Optional[List[str]] = None, subfolder: str = "") -> Path:
    """
    Resuelve una ruta de archivo para el toolbox.
    Si el archivo se encuentra fuera de storage/input/ (ej. ~/Downloads/archivo),
    lo importa automáticamente a storage/input/ (o subcarpeta).
    """
    target_dir = settings.INPUT_DIR / subfolder if subfolder else settings.INPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    expanded_path = Path(os.path.expanduser(path_or_name.strip("'\""))).resolve()

    if expanded_path.is_file():
        try:
            expanded_path.relative_to(settings.STORAGE_DIR.resolve())
            return expanded_path
        except ValueError:
            # Está fuera de storage, lo importamos/copiamos
            dest = target_dir / expanded_path.name
            if not dest.exists() or dest.stat().st_mtime < expanded_path.stat().st_mtime:
                shutil.copy2(expanded_path, dest)
            return dest

    # Si no es una ruta externa absoluta existente, buscar dentro de storage/input
    local_path = settings.INPUT_DIR / path_or_name
    if local_path.is_file():
        return local_path

    # Probar con extensiones permitidas
    if allowed_extensions:
        for ext in allowed_extensions:
            cand = settings.INPUT_DIR / f"{path_or_name}{ext}"
            if cand.is_file():
                return cand
            if subfolder:
                cand_sub = target_dir / f"{path_or_name}{ext}"
                if cand_sub.is_file():
                    return cand_sub

    return local_path
