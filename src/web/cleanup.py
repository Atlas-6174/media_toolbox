import time

from src.core.config import settings


def cleanup_old_files(max_age_seconds: int = 3600) -> int:
    """
    Elimina archivos temporales en storage/input y storage/output que tengan
    más de max_age_seconds de antigüedad (por defecto 1 hora).
    Preserva los archivos .gitkeep.
    Retorna la cantidad de archivos eliminados.
    """
    now = time.time()
    deleted_count = 0

    for root_dir in [settings.INPUT_DIR, settings.OUTPUT_DIR]:
        if not root_dir.exists():
            continue
        for item in root_dir.rglob("*"):
            if item.is_file() and item.name != ".gitkeep" and item.name != ".DS_Store":
                try:
                    mtime = item.stat().st_mtime
                    if now - mtime > max_age_seconds:
                        item.unlink()
                        deleted_count += 1
                except Exception:
                    pass

    return deleted_count
