import re
import shutil
from pathlib import Path
from typing import Dict

from src.core.config import settings
from src.core.docker_runner import DockerRunner


class PrivacyTool:
    SERVICE_NAME = "privacy"

    def clean(self, input_file: Path, output_file: Path) -> None:
        """Elimina metadatos (EXIF, GPS, autor, etc.) de imágenes, PDFs, audios o videos usando MAT2."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Copiar al destino y limpiar in-place
        shutil.copy2(input_file, output_file)

        try:
            container_output = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_output = Path("output/limpios") / output_file.name

        args = ["mat2", "--inplace", str(container_output)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def inspect(self, input_file: Path) -> Dict[str, str]:
        """Inspecciona y devuelve los metadatos detectados en el archivo usando MAT2."""
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        args = ["mat2", "-s", str(container_input)]
        metadata: Dict[str, str] = {}
        line_regex = re.compile(r"^\s+([^:]+):\s*(.*)$")

        for line in DockerRunner.run_service_stream(self.SERVICE_NAME, args):
            match = line_regex.match(line)
            if match:
                key = match.group(1).strip()
                val = match.group(2).strip()
                metadata[key] = val

        return metadata
