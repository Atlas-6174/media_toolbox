import subprocess
import sys
from pathlib import Path


def notify(title: str, message: str) -> None:
    """Envía una notificación de escritorio en macOS/Linux de forma no bloqueante."""
    try:
        if sys.platform == "darwin":
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def open_directory(path: Path) -> None:
    """Abre la carpeta en el explorador del sistema (Finder en macOS)."""
    try:
        resolved = str(path.resolve())
        if sys.platform == "darwin":
            subprocess.run(["open", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
