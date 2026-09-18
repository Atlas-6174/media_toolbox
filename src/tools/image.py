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

        in_ext = input_file.suffix.lower()
        ext = output_file.suffix.lower()

        if in_ext in [".heic", ".heif"]:
            if ext in [".jpg", ".jpeg"]:
                args = ["heif-convert", "-q", str(calidad), str(container_input), str(container_output)]
                DockerRunner.run_service("tools", args)
                return
            elif ext == ".png":
                args = ["heif-convert", str(container_input), str(container_output)]
                DockerRunner.run_service("tools", args)
                return
            else:
                # Para webp u otros formatos, convertir primero a JPG intermedio
                temp_jpg = output_file.with_suffix(".jpg")
                temp_c_out = container_output.with_suffix(".jpg")
                args = ["heif-convert", "-q", str(calidad), str(container_input), str(temp_c_out)]
                DockerRunner.run_service("tools", args)
                self.convert(temp_jpg, output_file, calidad=calidad, ancho=ancho)
                if temp_jpg.exists():
                    temp_jpg.unlink()
                return

        args = ["-y", "-i", str(container_input)]

        if ancho:
            args.extend(["-vf", f"scale={ancho}:-1"])

        if ext == ".webp":
            args.extend(["-c:v", "libwebp", "-quality", str(calidad)])
        elif ext in [".jpg", ".jpeg"]:
            qscale = max(1, min(31, int(31 - (calidad * 30 / 100))))
            args.extend(["-q:v", str(qscale)])

        args.append(str(container_output))
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def watermark(
        self,
        input_file: Path,
        output_file: Path,
        texto: Optional[str] = None,
        logo_file: Optional[Path] = None,
        posicion: str = "bottomright",
        opacidad: int = 70,
    ) -> None:
        """Superpone una marca de agua de texto o de imagen (logo) sobre una imagen usando ImageMagick."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/marcas_agua") / output_file.name

        gravities = {
            "bottomright": "southeast",
            "bottomleft": "southwest",
            "topright": "northeast",
            "topleft": "northwest",
            "center": "center",
        }
        gravity = gravities.get(posicion, "southeast")

        if logo_file is not None:
            try:
                container_logo = logo_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
            except ValueError:
                container_logo = Path("input") / logo_file.name

            args = [
                "composite",
                "-gravity", gravity,
                "-geometry", "+10+10",
                "-dissolve", str(max(1, min(100, opacidad))),
                str(container_logo),
                str(container_input),
                str(container_output),
            ]
        else:
            args = [
                "convert",
                str(container_input),
                "-gravity", gravity,
                "-pointsize", "28",
                "-fill", f"rgba(255,255,255,{opacidad / 100:.2f})",
                "-undercolor", f"rgba(0,0,0,{opacidad / 100 * 0.5:.2f})",
                "-annotate", "+10+10", texto or "MediaBox",
                str(container_output),
            ]
        DockerRunner.run_service("tools", args)
