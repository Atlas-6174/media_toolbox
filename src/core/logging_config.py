import logging
from logging.handlers import RotatingFileHandler

from src.core.config import settings

LOG_DIR = settings.STORAGE_DIR / "logs"
LOG_FILE = LOG_DIR / "web.log"

_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configura el logger "mediabox": consola (stdout, capturado por
    `docker compose logs` / journald) y archivo rotativo en storage/logs/web.log
    para poder diagnosticar fallos sin acceso interactivo al proceso.
    Idempotente: llamarla varias veces no duplica handlers.
    """
    global _configured
    logger = logging.getLogger("mediabox")
    if _configured:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    _configured = True
    return logger
