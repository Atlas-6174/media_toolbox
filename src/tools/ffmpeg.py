import re
from pathlib import Path

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
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/audios") / output_file.name

        ext = output_file.suffix.lower()
        codec_args = []
        if ext == ".mp3":
            codec_args = ["-q:a", "0", "-map", "a"]
        elif ext == ".wav":
            codec_args = ["-vn"]
        elif ext in [".m4a", ".aac"]:
            codec_args = ["-c:a", "aac", "-b:a", "256k", "-vn"]
        else:
            codec_args = ["-q:a", "0", "-map", "a"]

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
