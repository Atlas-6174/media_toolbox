import json
import re

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.core.docker_runner import DockerRunner


class DownloaderTool:
    SERVICE_NAME = "yt-dlp"

    def inspect(self, url: str) -> dict:
        """Obtiene metadatos básicos de un video para vista previa sin descargarlo."""
        args = [url, "--no-cache-dir", "--no-warnings", "--no-playlist", "--dump-single-json"]
        output = []
        try:
            for linea in DockerRunner.run_service_stream(self.SERVICE_NAME, args):
                output.append(linea)
            full_text = "".join(output).strip()
            json_start = full_text.find("{")
            json_end = full_text.rfind("}")
            if json_start != -1 and json_end != -1:
                data = json.loads(full_text[json_start : json_end + 1])
                dur_str = data.get("duration_string")
                if not dur_str and data.get("duration"):
                    dur = int(data["duration"])
                    dur_str = f"{dur // 60}:{dur % 60:02d}"
                return {
                    "title": data.get("title") or "Sin título",
                    "thumbnail": data.get("thumbnail"),
                    "duration": data.get("duration"),
                    "duration_string": dur_str,
                    "uploader": data.get("uploader") or data.get("channel"),
                    "description": (data.get("description") or "")[:200],
                }
        except Exception as e:
            return {"title": "Enlace de video", "thumbnail": None, "error": str(e)}
        return {"title": "Enlace de video", "thumbnail": None}

    def descargar(
        self, url: str, solo_audio: bool = False, calidad: str = "max", permitir_playlist: bool = False
    ) -> None:
        args = [url, "--no-cache-dir", "--no-warnings", "--newline", "--embed-metadata"]

        if not permitir_playlist:
            args.append("--no-playlist")

        if solo_audio:
            args.extend(["-o", "input/audios/%(title)s.%(ext)s", "-x", "--audio-format", "mp3", "--audio-quality", "0"])
            desc_tipo = "audio MP3"
        else:
            args.extend(["-o", "input/videos/%(title)s.%(ext)s"])
            if calidad == "1080p":
                formato = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
            elif calidad == "720p":
                formato = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
            else:
                formato = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            args.extend(["-f", formato])
            desc_tipo = f"video ({calidad})"

        regex_progreso = re.compile(r"\[download\]\s+([\d\.]+)%")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None, style="black", complete_style="green"),
            TaskProgressColumn(),
            expand=True,
        ) as progress:
            tarea = progress.add_task("Conectando con el servidor...", total=100.0)

            for linea in DockerRunner.run_service_stream(self.SERVICE_NAME, args):
                match = regex_progreso.search(linea)
                if match:
                    porcentaje = float(match.group(1))
                    progress.update(tarea, completed=porcentaje, description=f"Descargando {desc_tipo}...")
                elif "Extracting URL" in linea:
                    progress.update(tarea, description="Analizando enlace...")
                elif "Downloading webpage" in linea:
                    progress.update(tarea, description="Obteniendo metadatos...")
                elif "Destination:" in linea:
                    progress.update(tarea, description=f"Procesando {desc_tipo}...")
                elif "Merging formats" in linea or "ExtractAudio" in linea:
                    progress.update(tarea, description="[yellow]Finalizando archivo multimedia...")

            progress.update(tarea, completed=100.0, description="[bold green]¡Descarga completada!")


# Alias para retrocompatibilidad
DescargadorTool = DownloaderTool
downloader = DownloaderTool
