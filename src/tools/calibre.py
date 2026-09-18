import re
from pathlib import Path
from typing import Optional

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.core.config import settings
from src.core.docker_runner import DockerRunner
from src.tools.base import BaseTool


class CalibreTool(BaseTool):
    SERVICE_NAME = "calibre"

    def convert(
        self, input_file: Path, output_file: Path, paper_size: str = "a4", output_profile: Optional[str] = None
    ) -> None:
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/pdfs") / output_file.name

        args = [
            str(container_input),
            str(container_output),
            "--paper-size",
            paper_size,
            "--pdf-page-numbers",
            "--margin-top",
            "20",
            "--margin-bottom",
            "20",
            "--margin-left",
            "20",
            "--margin-right",
            "20",
        ]

        if output_profile:
            args.extend(["--output-profile", output_profile])

        regex_porcentaje = re.compile(r"(\d{1,3})%\s*(.*)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold magenta]{task.description}"),
            BarColumn(bar_width=None, style="black", complete_style="magenta"),
            TaskProgressColumn(),
            expand=True,
        ) as progress:
            tarea = progress.add_task(f"Convirtiendo '{input_file.name}'...", total=100.0)

            for linea in DockerRunner.run_service_stream(self.SERVICE_NAME, args):
                match = regex_porcentaje.search(linea)
                if match:
                    pct = float(match.group(1))
                    detalle = match.group(2).strip()
                    desc = f"Convirtiendo: {detalle[:30]}..." if detalle else "Convirtiendo documento..."
                    progress.update(tarea, completed=min(pct, 100.0), description=desc)

            progress.update(tarea, completed=100.0, description=f"[bold green]'{input_file.name}' convertido!")
