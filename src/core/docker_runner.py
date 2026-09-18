import os
import subprocess
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel

console = Console()

class DockerCommandExecutionError(Exception):
    def __init__(self, message: str, logs: Optional[List[str]] = None):
        super().__init__(message)
        self.logs = logs or []

def is_docker_running() -> bool:
    """Verifica si el daemon de Docker está respondiendo."""
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def ensure_docker() -> None:
    """Verifica que Docker esté activo; de lo contrario, muestra un mensaje descriptivo y termina."""
    if not is_docker_running():
        console.print(Panel(
            "[bold red]❌ Docker no está en ejecución o no se puede conectar al daemon.[/bold red]\n\n"
            "[yellow]Por favor, asegúrate de que Docker Desktop esté iniciado antes de ejecutar comandos.[/yellow]",
            title="[bold red]Docker Requerido[/bold red]",
            border_style="red"
        ))
        raise SystemExit(1)

class DockerRunner:
    @classmethod
    def run_service(cls, service_name: str, args: List[str]):
        """Ejecuta el contenedor esperando que termine."""
        for _ in cls.run_service_stream(service_name, args):
            pass

    @staticmethod
    def run_service_stream(service_name: str, args: List[str]):
        """Ejecuta el contenedor y devuelve su salida línea por línea en tiempo real con portabilidad global."""
        from src.core.config import settings

        env = os.environ.copy()
        env["UID"] = settings.UID
        env["GID"] = settings.GID

        cmd = [
            "docker", "compose",
            "-f", str(settings.DOCKER_COMPOSE_FILE),
            "--progress", "quiet",
            "run", "--rm",
            service_name,
            *args
        ]

        process = subprocess.Popen(
            cmd,
            cwd=str(settings.BASE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        collected_logs = []
        for line in iter(process.stdout.readline, ''):
            collected_logs.append(line)
            yield line

        process.wait()
        if process.returncode != 0:
            raise DockerCommandExecutionError(
                f"Error en {service_name}: código {process.returncode}",
                logs=collected_logs
            )