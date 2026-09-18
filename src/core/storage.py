from pathlib import Path
from typing import Dict, List

from src.core.config import STANDARD_SUBDIRS, settings


def format_size(size_bytes: int) -> str:
    """Convierte bytes a formato legible (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def ensure_default_directories():
    """
    Garantiza que todas las carpetas clasificatorias por defecto
    existan en storage/input/ y storage/output/ con su respectivo .gitkeep.
    """
    all_subdirs = list(STANDARD_SUBDIRS)
    if "uploads" not in all_subdirs:
        all_subdirs.append("uploads")
    if "temp" not in all_subdirs:
        all_subdirs.append("temp")

    # Carpetas en input
    for sub in all_subdirs:
        folder = settings.INPUT_DIR / sub
        folder.mkdir(parents=True, exist_ok=True)
        gitkeep = folder / ".gitkeep"
        if not any(folder.iterdir()):
            gitkeep.touch(exist_ok=True)

    # Carpetas en output
    for sub in STANDARD_SUBDIRS:
        folder = settings.OUTPUT_DIR / sub
        folder.mkdir(parents=True, exist_ok=True)
        gitkeep = folder / ".gitkeep"
        if not any(folder.iterdir()):
            gitkeep.touch(exist_ok=True)


def purge_storage(target: str = "all") -> Dict:
    """
    Purga archivos acumulados en el almacenamiento conservando intactas todas
    las carpetas clasificatorias y los archivos .gitkeep.

    :param target: 'all' (input + output), 'input', u 'output'.
    :return: Diccionario con estadísticas de la purga.
    """
    deleted_count = 0
    freed_bytes = 0

    dirs_to_clean: List[Path] = []
    if target in ["all", "input"]:
        dirs_to_clean.append(settings.INPUT_DIR)
        # Limpiar también storage/temp si existe en la raíz de storage
        root_temp = settings.STORAGE_DIR / "temp"
        if root_temp.exists():
            dirs_to_clean.append(root_temp)

    if target in ["all", "output"]:
        dirs_to_clean.append(settings.OUTPUT_DIR)

    for base_dir in dirs_to_clean:
        if not base_dir.exists():
            continue

        for item in list(base_dir.rglob("*")):
            if item.is_file():
                # Conservar archivos estructurales .gitkeep
                if item.name == ".gitkeep":
                    continue

                try:
                    freed_bytes += item.stat().st_size
                    item.unlink()
                    deleted_count += 1
                except Exception:
                    pass

    # Re-asegurar que todas las carpetas por defecto queden creadas y listas
    ensure_default_directories()

    return {
        "status": "ok",
        "target": target,
        "deleted_count": deleted_count,
        "freed_bytes": freed_bytes,
        "freed_human": format_size(freed_bytes),
    }
