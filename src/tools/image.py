from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.core.docker_runner import DockerRunner


class ImageTool:
    SERVICE_NAME = "ffmpeg"

    def convert(self, input_file: Path, output_file: Path, calidad: int = 80, ancho: Optional[int] = None) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/imagenes") / output_file.name

        args = ["-y", "-i", str(container_input)]

        if ancho:
            args.extend(["-vf", f"scale={ancho}:-1"])

        ext = output_file.suffix.lower()
        if ext == ".webp":
            args.extend(["-c:v", "libwebp", "-quality", str(calidad)])
        elif ext in [".jpg", ".jpeg"]:
            # FFmpeg usa escala qscale (1 mejor, 31 peor)
            qscale = max(1, min(31, int(31 - (calidad * 30 / 100))))
            args.extend(["-q:v", str(qscale)])

        args.append(str(container_output))
        DockerRunner.run_service(self.SERVICE_NAME, args)
