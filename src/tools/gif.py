from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.core.docker_runner import DockerRunner


class GifTool:
    SERVICE_NAME = "ffmpeg"

    def create_gif(
        self,
        input_file: Path,
        output_file: Path,
        desde: Optional[str] = None,
        hasta: Optional[str] = None,
        duracion: Optional[str] = None,
        fps: int = 15,
        ancho: int = 480,
    ) -> None:
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/gifs") / output_file.name

        args = ["-y"]
        if desde:
            args.extend(["-ss", desde])
        if hasta:
            args.extend(["-to", hasta])
        elif duracion:
            args.extend(["-t", duracion])

        filter_complex = f"fps={fps},scale={ancho}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"

        args.extend(["-i", str(container_input), "-vf", filter_complex, "-loop", "0", str(container_output)])

        DockerRunner.run_service(self.SERVICE_NAME, args)
