from pathlib import Path
from typing import List

from src.core.config import settings
from src.core.docker_runner import DockerRunner


class PdfTool:
    SERVICE_NAME = "pdf"

    def unir(self, input_files: List[Path], output_file: Path) -> None:
        args = []
        for f in input_files:
            try:
                c_in = f.resolve().relative_to(settings.STORAGE_DIR.resolve())
            except ValueError:
                c_in = Path("input") / f.name
            args.append(str(c_in))

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdfs") / output_file.name
        args.append(str(c_out))

        DockerRunner.run_service(self.SERVICE_NAME, args)
