import re
from pathlib import Path
from typing import Optional

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.core.config import settings
from src.core.docker_runner import DockerRunner
from src.tools.base import BaseTool


def tiempo_a_segundos(tiempo_str: str) -> float:
    """Convierte un formato HH:MM:SS.xx a segundos totales."""
    try:
        h, m, s = tiempo_str.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return 0.0


class FFmpegTool(BaseTool):
    SERVICE_NAME = "ffmpeg"

    def convert(self, input_file: Path, output_file: Path, **kwargs) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/audios") / output_file.name

        ext = output_file.suffix.lower()
        normalizar = kwargs.get("normalizar", False)
        filter_args = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"] if normalizar else []

        codec_args = []
        if ext == ".mp3":
            codec_args = [*filter_args, "-q:a", "0", "-map", "a"]
        elif ext == ".wav":
            codec_args = [*filter_args, "-vn"]
        elif ext in [".m4a", ".aac"]:
            codec_args = [*filter_args, "-c:a", "aac", "-b:a", "256k", "-vn"]
        else:
            codec_args = [*filter_args, "-q:a", "0", "-map", "a"]

        args = ["-y", "-i", str(container_input), *codec_args, "-progress", "pipe:1", "-nostats", str(container_output)]

        regex_duracion = re.compile(r"Duration:\s+(\d{2}:\d{2}:\d{2}\.\d+)")
        regex_tiempo = re.compile(r"out_time=(\d{2}:\d{2}:\d{2}\.\d+)")

        duracion_total = 0.0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=None, style="black", complete_style="cyan"),
            TaskProgressColumn(),
            expand=True,
        ) as progress:
            tarea = progress.add_task(f"Analizando '{input_file.name}'...", total=100.0)

            for linea in DockerRunner.run_service_stream(self.SERVICE_NAME, args):
                if duracion_total == 0.0:
                    match_dur = regex_duracion.search(linea)
                    if match_dur:
                        duracion_total = tiempo_a_segundos(match_dur.group(1))
                        progress.update(tarea, description=f"Extrayendo audio ({ext.lstrip('.').upper()})...")
                else:
                    match_tiempo = regex_tiempo.search(linea)
                    if match_tiempo:
                        tiempo_actual = tiempo_a_segundos(match_tiempo.group(1))
                        if duracion_total > 0:
                            porcentaje = min((tiempo_actual / duracion_total) * 100, 100.0)
                            progress.update(tarea, completed=porcentaje)

            progress.update(tarea, completed=100.0, description=f"[bold green]'{output_file.name}' extraído con éxito!")

    def mute(self, input_file: Path, output_file: Path) -> None:
        """Silencia un video eliminando la pista de audio sin recodificar video."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/silenciados") / output_file.name

        args = ["-y", "-i", str(container_input), "-c:v", "copy", "-an", str(container_output)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def snapshot(self, input_file: Path, output_file: Path, tiempo: str = "00:00:01") -> None:
        """Extrae un fotograma en alta calidad en un segundo específico."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/capturas") / output_file.name

        args = ["-y", "-ss", tiempo, "-i", str(container_input), "-vframes", "1", "-update", "1", "-q:v", "2", str(container_output)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def change_speed(self, input_file: Path, output_file: Path, velocidad: float = 1.5) -> None:
        """Modifica la velocidad de reproducción de un audio sin alterar el tono vocal usando el filtro atempo."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/audios") / output_file.name

        v = max(0.25, min(4.0, float(velocidad)))
        if v > 2.0:
            filter_str = f"atempo=2.0,atempo={v / 2.0:.2f}"
        elif v < 0.5:
            filter_str = f"atempo=0.5,atempo={v / 0.5:.2f}"
        else:
            filter_str = f"atempo={v:.2f}"

        args = [
            "-y",
            "-i", str(container_input),
            "-filter:a", filter_str,
            "-vn",
            str(container_output),
        ]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def _to_container_path(self, path: Path, fallback: str) -> Path:
        try:
            return path.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            return Path(fallback) / path.name

    def extract_subtitles(self, input_file: Path, output_file: Path, pista: int = 0) -> None:
        """Extrae una pista de subtítulos de un video a un archivo .srt/.vtt independiente."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        container_input = self._to_container_path(input_file, "input")
        container_output = self._to_container_path(output_file, "output/subtitulos")

        args = ["-y", "-i", str(container_input), "-map", f"0:s:{pista}", str(container_output)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def burn_subtitles(self, input_file: Path, subtitle_file: Path, output_file: Path) -> None:
        """Incrusta ('quema') una pista de subtítulos directamente sobre el video, visible en cualquier reproductor."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        container_input = self._to_container_path(input_file, "input")
        container_subs = self._to_container_path(subtitle_file, "input")
        container_output = self._to_container_path(output_file, "output/marcas_agua")

        args = [
            "-y",
            "-i", str(container_input),
            "-vf", f"subtitles={container_subs}",
            "-c:a", "copy",
            str(container_output),
        ]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def watermark(
        self,
        input_file: Path,
        output_file: Path,
        texto: Optional[str] = None,
        logo_file: Optional[Path] = None,
        posicion: str = "bottomright",
        opacidad: float = 0.7,
    ) -> None:
        """Superpone una marca de agua de texto o de imagen (logo) sobre un video."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        container_input = self._to_container_path(input_file, "input")
        container_output = self._to_container_path(output_file, "output/marcas_agua")

        margin = 10
        positions = {
            "bottomright": ("main_w-overlay_w-{m}", "main_h-overlay_h-{m}"),
            "bottomleft": ("{m}", "main_h-overlay_h-{m}"),
            "topright": ("main_w-overlay_w-{m}", "{m}"),
            "topleft": ("{m}", "{m}"),
            "center": ("(main_w-overlay_w)/2", "(main_h-overlay_h)/2"),
        }
        x_expr, y_expr = positions.get(posicion, positions["bottomright"])
        x_expr, y_expr = x_expr.format(m=margin), y_expr.format(m=margin)

        if logo_file is not None:
            container_logo = self._to_container_path(logo_file, "input")
            args = [
                "-y",
                "-i", str(container_input),
                "-i", str(container_logo),
                "-filter_complex",
                f"[1:v]format=rgba,colorchannelmixer=aa={opacidad}[wm];[0:v][wm]overlay={x_expr}:{y_expr}",
                "-codec:a", "copy",
                str(container_output),
            ]
        else:
            texto_escapado = (texto or "MediaBox").replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
            text_positions = {
                "bottomright": f"x=w-tw-{margin}:y=h-th-{margin}",
                "bottomleft": f"x={margin}:y=h-th-{margin}",
                "topright": f"x=w-tw-{margin}:y={margin}",
                "topleft": f"x={margin}:y={margin}",
                "center": "x=(w-tw)/2:y=(h-th)/2",
            }
            pos_expr = text_positions.get(posicion, text_positions["bottomright"])
            draw = (
                f"drawtext=text='{texto_escapado}':fontcolor=white@{opacidad}:fontsize=24:"
                f"box=1:boxcolor=black@{opacidad * 0.4}:boxborderw=6:{pos_expr}"
            )
            args = [
                "-y",
                "-i", str(container_input),
                "-vf", draw,
                "-codec:a", "copy",
                str(container_output),
            ]
        DockerRunner.run_service(self.SERVICE_NAME, args)
