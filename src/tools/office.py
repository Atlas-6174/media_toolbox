import uuid
from pathlib import Path

from src.core.config import settings
from src.core.docker_runner import DockerRunner
from src.tools.base import BaseTool

SUPPORTED_OFFICE_EXTENSIONS = [
    ".docx", ".doc", ".odt", ".rtf",
    ".xlsx", ".xls", ".ods", ".csv",
    ".pptx", ".ppt", ".odp",
]


class OfficeTool(BaseTool):
    """Convierte documentos de oficina (Word, Excel, PowerPoint, OpenDocument...) a PDF
    manteniendo el formato visual original, usando LibreOffice en modo headless."""

    SERVICE_NAME = "libreoffice"

    def convert(self, input_file: Path, output_file: Path, **kwargs) -> None:
        self.convert_to_pdf(input_file, output_file)

    def convert_to_pdf(self, input_file: Path, output_file: Path) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            container_input = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_input = Path("input") / input_file.name

        try:
            container_outdir = output_file.parent.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            container_outdir = Path("output/pdfs")

        # -env:UserInstallation con una ruta única por ejecución: LibreOffice headless no puede
        # crear su perfil de usuario con el UID/GID del host (sin entrada en /etc/passwd), y además
        # dos conversiones simultáneas competirían por el mismo perfil/lock si compartieran ruta.
        profile_path = f"/tmp/lo_profile_{uuid.uuid4().hex}"  # nosec B108 -- ruta impredecible por uuid4, contenedor efímero y aislado
        args = [
            f"-env:UserInstallation=file://{profile_path}",
            "--convert-to", "pdf",
            "--outdir", f"/workspace/{container_outdir}",
            f"/workspace/{container_input}",
        ]
        DockerRunner.run_service(self.SERVICE_NAME, args)

        # LibreOffice nombra el archivo de salida a partir del nombre del de entrada (mismo stem);
        # si el output_file solicitado usa otro nombre, lo renombramos.
        generated = output_file.parent / f"{input_file.stem}.pdf"
        if generated.exists() and generated != output_file:
            generated.replace(output_file)
