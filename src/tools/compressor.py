import re
from pathlib import Path

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.core.config import settings
from src.core.docker_runner import DockerRunner
from src.tools.ffmpeg import tiempo_a_segundos


class VideoCompressorTool:
    SERVICE_NAME = "ffmpeg"

    def compress(self, input_file: Path, output_file: Path, perfil: str = "equilibrada") -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/comprimidos") / output_file.name

        audio_bitrate = "128k"
        if perfil == "ligera":
            crf = "20"
            preset = "slow"
            extra_vf = []
        elif perfil == "maxima":
            crf = "30"
            preset = "faster"
            extra_vf = ["-vf", "scale=-2:720"]
        elif perfil == "whatsapp":
            crf = "32"
            preset = "faster"
            extra_vf = ["-vf", "scale=-2:480"]
            audio_bitrate = "96k"
        elif perfil in ["vertical_reels", "reels", "tiktok"]:
            crf = "24"
            preset = "medium"
            extra_vf = ["-vf", "crop=ih*9/16:ih,scale=1080:1920"]
        else:  # equilibrada
            crf = "25"
            preset = "medium"
            extra_vf = []

        args = [
            "-y",
            "-i",
            str(container_input),
            "-c:v",
            "libx264",
            "-crf",
            crf,
            "-preset",
            preset,
            *extra_vf,
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-progress",
            "pipe:1",
            "-nostats",
            str(container_output),
        ]

        regex_duracion = re.compile(r"Duration:\s+(\d{2}:\d{2}:\d{2}\.\d+)")
        regex_tiempo = re.compile(r"out_time=(\d{2}:\d{2}:\d{2}\.\d+)")

        duracion_total = 0.0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold yellow]{task.description}"),
            BarColumn(bar_width=None, style="black", complete_style="yellow"),
            TaskProgressColumn(),
            expand=True,
        ) as progress:
            tarea = progress.add_task(f"Comprimiendo {input_file.name}...", total=100.0)

            for linea in DockerRunner.run_service_stream(self.SERVICE_NAME, args):
                if duracion_total == 0.0:
                    match_dur = regex_duracion.search(linea)
                    if match_dur:
                        duracion_total = tiempo_a_segundos(match_dur.group(1))
                        progress.update(tarea, description=f"Comprimiendo ({perfil})...")
                else:
                    match_tiempo = regex_tiempo.search(linea)
                    if match_tiempo:
                        tiempo_actual = tiempo_a_segundos(match_tiempo.group(1))
                        if duracion_total > 0:
                            porcentaje = min((tiempo_actual / duracion_total) * 100, 100.0)
                            progress.update(tarea, completed=porcentaje)

            progress.update(tarea, completed=100.0, description=f"[bold green]{output_file.name} comprimido!")
