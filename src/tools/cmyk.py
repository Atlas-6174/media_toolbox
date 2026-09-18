import shutil
import uuid
from pathlib import Path
from typing import Optional

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.core.config import settings
from src.core.docker_runner import DockerRunner


class CmykTool:
    SERVICE_NAME = "cmyk"

    def convert(
        self,
        input_file: Path,
        output_file: Path,
        formato: str = "pdf",
        perfil: str = "fogra39",
        dpi: int = 300,
    ) -> None:
        """
        Convierte una ilustración o diseño digital (SVG de Inkscape, PDF o imagen)
        desde el espacio de color RGB a CMYK puro para imprenta profesional.
        """
        # Asegurar que el archivo de entrada esté dentro de storage/
        try:
            rel_in = f"/workspace/{input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())}"
            temp_input_created = False
        except ValueError:
            target_in = settings.INPUT_DIR / "cmyk" / input_file.name
            target_in.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_file, target_in)
            rel_in = f"/workspace/input/cmyk/{input_file.name}"
            temp_input_created = True

        try:
            rel_out = f"/workspace/{output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())}"
        except ValueError:
            rel_out = f"/workspace/output/cmyk/{output_file.name}"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        ext_in = input_file.suffix.lower()
        formato = formato.lower().lstrip(".")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None, style="black", complete_style="green"),
            TaskProgressColumn(),
            expand=True,
        ) as progress:
            task = progress.add_task("Preparando archivo para imprenta CMYK...", total=100.0)

            intermediate_pdf_rel: Optional[str] = None
            intermediate_pdf_path: Optional[Path] = None

            try:
                # Paso 1: Si es SVG (Inkscape), exportar a PDF vectorial de alta precisión
                if ext_in == ".svg":
                    progress.update(task, completed=25.0, description="Exportando vectores con motor Inkscape...")
                    temp_pdf_name = f"temp_inkscape_{uuid.uuid4().hex[:8]}.pdf"
                    intermediate_pdf_path = settings.STORAGE_DIR / "input" / "cmyk" / temp_pdf_name
                    intermediate_pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    intermediate_pdf_rel = f"/workspace/input/cmyk/{temp_pdf_name}"

                    inkscape_args = [
                        "inkscape",
                        rel_in,
                        f"--export-filename={intermediate_pdf_rel}",
                        "--export-area-page",
                    ]
                    DockerRunner.run_service(self.SERVICE_NAME, inkscape_args)
                    source_for_cmyk = intermediate_pdf_rel
                elif ext_in == ".pdf":
                    source_for_cmyk = rel_in
                else:
                    # Imagen raster (PNG, JPG, TIFF)
                    source_for_cmyk = None

                # Paso 2: Conversión de Espacio de Color a CMYK
                progress.update(task, completed=60.0, description="Convirtiendo espacio de color a CMYK...")

                if source_for_cmyk is not None:
                    # Flujo Ghostscript para vectores y documentos PDF
                    if formato == "pdf":
                        # Salida vectorial PDF DeviceCMYK
                        gs_args = [
                            "gs",
                            "-dSAFER",
                            "-dBATCH",
                            "-dNOPAUSE",
                            "-sDEVICE=pdfwrite",
                            "-dCompatibilityLevel=1.4",
                            "-sColorConversionStrategy=CMYK",
                            "-dProcessColorModel=/DeviceCMYK",
                            "-dOverrideICC=true",
                            f"-o{rel_out}",
                            source_for_cmyk,
                        ]
                    elif formato in ["tiff", "tif"]:
                        # Salida TIFF CMYK a resolución especificada (por defecto 300 DPI)
                        gs_args = [
                            "gs",
                            "-dSAFER",
                            "-dBATCH",
                            "-dNOPAUSE",
                            "-sDEVICE=tiff32nc",
                            f"-r{dpi}",
                            f"-o{rel_out}",
                            source_for_cmyk,
                        ]
                    else:
                        # Salida JPG CMYK a resolución de imprenta
                        gs_args = [
                            "gs",
                            "-dSAFER",
                            "-dBATCH",
                            "-dNOPAUSE",
                            "-sDEVICE=jpegcmyk",
                            f"-r{dpi}",
                            "-dJPEGQ=95",
                            f"-o{rel_out}",
                            source_for_cmyk,
                        ]
                    DockerRunner.run_service(self.SERVICE_NAME, gs_args)
                else:
                    # Flujo ImageMagick para imágenes rasterizadas (PNG / JPG -> CMYK)
                    im_args = [
                        "convert",
                        rel_in,
                        "-colorspace",
                        "CMYK",
                        "-density",
                        str(dpi),
                        rel_out,
                    ]
                    DockerRunner.run_service(self.SERVICE_NAME, im_args)

                progress.update(task, completed=100.0, description="[bold green]¡Diseño CMYK listo para imprenta!")

            finally:
                # Limpiar temporales
                if intermediate_pdf_path and intermediate_pdf_path.exists():
                    intermediate_pdf_path.unlink(missing_ok=True)
                if temp_input_created and input_file.exists():
                    pass
