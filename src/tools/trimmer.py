from pathlib import Path
from typing import Optional
from src.core.docker_runner import DockerRunner
from src.core.config import settings

class TrimmerTool:
    SERVICE_NAME = "ffmpeg"

    def trim(
        self,
        input_file: Path,
        output_file: Path,
        desde: Optional[str] = None,
        hasta: Optional[str] = None,
        duracion: Optional[str] = None
    ) -> None:
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output") / output_file.name

        args = ["-y"]
        if desde:
            args.extend(["-ss", desde])
        if hasta:
            args.extend(["-to", hasta])
        elif duracion:
            args.extend(["-t", duracion])

        args.extend([
            "-i", str(container_input),
            "-c", "copy",
            "-map", "0",
            "-avoid_negative_ts", "make_zero",
            str(container_output)
        ])

        DockerRunner.run_service(self.SERVICE_NAME, args)
