import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import settings
from src.core.docker_runner import DockerRunner


class PdfTool:
    SERVICE_NAME = "pdf"

    def unir(self, input_files: List[Path], output_file: Path) -> None:
        file_args = []
        for f in input_files:
            try:
                c_in = f.resolve().relative_to(settings.STORAGE_DIR.resolve())
            except ValueError:
                c_in = Path("input") / f.name
            file_args.append(str(c_in))

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdfs") / output_file.name

        args = ["pdfunite", *file_args, str(c_out)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def _build_gs_args(self, c_in: Path, c_out: Path, perfil: str) -> List[str]:
        """Construye los argumentos de Ghostscript optimizados por resolución y espacio."""
        if perfil == "screen":
            gs_setting = "/screen"
            dpi = "72"
        elif perfil == "printer":
            gs_setting = "/printer"
            dpi = "150"
        else:  # ebook o equilibrada
            gs_setting = "/ebook"
            dpi = "96"

        return [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.5",
            f"-dPDFSETTINGS={gs_setting}",
            f"-dColorImageResolution={dpi}",
            f"-dGrayImageResolution={dpi}",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={c_out}",
            str(c_in),
        ]

    def compress(self, input_file: Path, output_file: Path, perfil: str = "ebook") -> Dict[str, Any]:
        """Comprime un PDF asegurando que el tamaño resultante NUNCA sea mayor al original."""
        try:
            c_in = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_in = Path("input") / input_file.name

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdf_comprimidos") / output_file.name

        args = self._build_gs_args(c_in, c_out, perfil)
        DockerRunner.run_service(self.SERVICE_NAME, args)

        in_size = input_file.stat().st_size if input_file.exists() else 0
        out_size = output_file.stat().st_size if output_file.exists() else 0

        # Salvaguarda 1: Si el archivo aumentó de tamaño y no estábamos en el modo más agresivo,
        # intentamos automáticamente con compresión de pantalla (72 DPI).
        if in_size > 0 and out_size >= in_size and perfil != "screen":
            fallback_args = self._build_gs_args(c_in, c_out, "screen")
            DockerRunner.run_service(self.SERVICE_NAME, fallback_args)
            out_size = output_file.stat().st_size if output_file.exists() else 0

        # Salvaguarda 2: Si aún con máxima compresión el archivo es igual o más pesado
        # (ej. PDF que ya está optimizado al máximo o solo contiene texto vectorial sin compresión posible),
        # conservamos el original para garantizar que NUNCA aumente el peso.
        was_already_optimal = False
        if in_size > 0 and out_size >= in_size:
            shutil.copyfile(input_file, output_file)
            out_size = in_size
            was_already_optimal = True

        saved_bytes = max(0, in_size - out_size)
        saved_pct = round((saved_bytes / in_size) * 100, 1) if in_size > 0 else 0.0

        return {
            "input_size": in_size,
            "output_size": out_size,
            "saved_bytes": saved_bytes,
            "saved_pct": saved_pct,
            "was_already_optimal": was_already_optimal,
        }

    def ocr(self, input_file: Path, output_file: Path, idioma: str = "spa+eng") -> Dict[str, object]:
        """Añade una capa de texto searchable a un PDF escaneado usando OCRmyPDF y Tesseract."""
        try:
            c_in = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_in = Path("input") / input_file.name

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdfs") / output_file.name

        # --skip-text: no falla si algunas páginas ya tienen texto
        args = ["ocrmypdf", "--skip-text", "-l", idioma, str(c_in), str(c_out)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

        in_size = input_file.stat().st_size if input_file.exists() else 0
        out_size = output_file.stat().st_size if output_file.exists() else 0

        return {
            "input_size": in_size,
            "output_size": out_size,
            "filename": output_file.name,
            "idioma": idioma,
        }

    def extract_pages(self, input_file: Path, output_file: Path, paginas: str = "1") -> Dict[str, object]:
        """Extrae un rango de páginas (ej. '1-5', '3,7,10', '1-z') usando qpdf."""
        try:
            c_in = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_in = Path("input") / input_file.name

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdfs") / output_file.name

        args = ["qpdf", str(c_in), "--pages", ".", paginas, "--", str(c_out)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

        in_size = input_file.stat().st_size if input_file.exists() else 0
        out_size = output_file.stat().st_size if output_file.exists() else 0

        return {
            "input_size": in_size,
            "output_size": out_size,
            "filename": output_file.name,
            "paginas": paginas,
        }

    def rotate(self, input_file: Path, output_file: Path, angulo: int = 90, paginas: str = "1-z") -> None:
        """Rota páginas de un PDF (ángulo múltiplo de 90) usando qpdf."""
        try:
            c_in = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_in = Path("input") / input_file.name

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdfs") / output_file.name

        args = [
            "qpdf",
            str(c_in),
            f"--rotate={angulo:+d}:{paginas}",
            str(c_out),
        ]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def protect(
        self,
        input_file: Path,
        output_file: Path,
        password_usuario: str,
        password_propietario: Optional[str] = None,
    ) -> None:
        """Protege un PDF con contraseña (AES-256) usando qpdf. Sin permisos de impresión/edición para quien
        solo tenga la contraseña de usuario."""
        try:
            c_in = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_in = Path("input") / input_file.name

        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            c_out = output_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out = Path("output/pdfs") / output_file.name

        owner_pw = password_propietario or password_usuario
        args = [
            "qpdf",
            "--encrypt",
            password_usuario,
            owner_pw,
            "256",
            "--",
            str(c_in),
            str(c_out),
        ]
        DockerRunner.run_service(self.SERVICE_NAME, args)

    def pdf_to_images(
        self,
        input_file: Path,
        output_dir: Path,
        formato: str = "png",
        dpi: int = 300,
    ) -> List[Path]:
        """Convierte las páginas de un PDF en imágenes individuales de alta resolución con pdftoppm."""
        try:
            c_in = input_file.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_in = Path("input") / input_file.name

        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            c_out_dir = output_dir.resolve().relative_to(settings.STORAGE_DIR.resolve())
        except ValueError:
            c_out_dir = Path("output/imagenes") / output_dir.name

        fmt_flag = f"-{formato.lower()}" if formato.lower() in ["png", "jpeg", "jpg", "tiff"] else "-png"
        prefix = "pagina"
        c_prefix = c_out_dir / prefix

        args = ["pdftoppm", fmt_flag, "-r", str(dpi), str(c_in), str(c_prefix)]
        DockerRunner.run_service(self.SERVICE_NAME, args)

        # Buscar las imágenes generadas
        ext = "jpg" if formato.lower() in ["jpeg", "jpg"] else formato.lower()
        generated = sorted(list(output_dir.glob(f"{prefix}*.{ext}")))
        return generated

