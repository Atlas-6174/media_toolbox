import subprocess
import sys
from pathlib import Path


def notify(title: str, message: str) -> None:
    """Envía una notificación de escritorio en macOS, Linux y Windows de forma no bloqueante."""
    try:
        if sys.platform == "darwin":
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            # Notificación en Windows vía PowerShell
            ps_cmd = (
                f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms"); '
                f'$notify = new-object system.windows.forms.notifyicon; '
                f'$notify.icon = [system.drawing.systemicons]::information; '
                f'$notify.visible = $true; '
                f'$notify.showballoontip(3000, "{title}", "{message}", [system.windows.forms.tooltipicon]::info)'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def open_directory(path: Path) -> None:
    """Abre la carpeta en el explorador del sistema (Finder en macOS, Explorer en Windows, xdg en Linux)."""
    try:
        resolved = str(path.resolve())
        if sys.platform == "darwin":
            subprocess.run(["open", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            subprocess.run(["explorer", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

