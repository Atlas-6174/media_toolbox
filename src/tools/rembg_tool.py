from pathlib import Path

from src.core.config import settings
from src.core.docker_runner import DockerRunner
from src.tools.base import BaseTool

# Modelo pre-horneado en la imagen en tiempo de build (ver docker/rembg/Dockerfile):
# el contenedor corre con network_mode: none, así que solo este modelo está disponible.
DEFAULT_MODEL = "u2net"


class RembgTool(BaseTool):
    """Elimina el fondo de una imagen usando rembg (modelo U2Net) en un contenedor aislado."""

    SERVICE_NAME = "rembg"

    def convert(self, input_file: Path, output_file: Path, **kwargs) -> None:
        self.remove_background(input_file, output_file)

    def remove_background(self, input_file: Path, output_file: Path) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/sin_fondo") / output_file.name

        args = [
            "i",
            "-m", DEFAULT_MODEL,
            str(container_input),
            str(container_output),
        ]
        DockerRunner.run_service(self.SERVICE_NAME, args)
