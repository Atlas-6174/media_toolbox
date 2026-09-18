"""
Herramienta de conversión a Markdown usando markitdown.
Soporta: PDF, DOCX, PPTX, XLSX, HTML, CSV, EPUB, TXT, imágenes, ZIP y URLs.
"""

from pathlib import Path


class MarkdownTool:
    """Convierte documentos y archivos a formato Markdown usando markitdown."""

    SUPPORTED_EXTENSIONS = [
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".csv",
        ".epub",
        ".txt",
        ".zip",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
    ]

    def convert(self, input_path: Path, output_path: Path) -> Path:
        """
        Convierte un archivo al formato Markdown.

        Args:
            input_path: Ruta al archivo de entrada.
            output_path: Ruta donde se guardará el archivo .md resultante.

        Returns:
            La ruta al archivo .md generado.

        Raises:
            ImportError: Si markitdown no está instalado.
            ValueError: Si el archivo de entrada no existe o el formato no es soportado.
            RuntimeError: Si la conversión falla.
        """
        try:
            from markitdown import MarkItDown
        except ImportError as e:
            raise ImportError(
                "La librería 'markitdown' no está instalada. "
                "Instala con: pip install 'markitdown[pdf,docx,pptx,xlsx]'"
            ) from e

        if not input_path.is_file():
            raise ValueError(f"El archivo de entrada no existe: {input_path}")

        ext = input_path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Extensión '{ext}' no soportada. Formatos válidos: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

        try:
            md = MarkItDown()
            result = md.convert(str(input_path))
            text = result.text_content or ""
        except Exception as e:
            raise RuntimeError(f"Error durante la conversión a Markdown: {e}") from e

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return output_path

    def convert_url(self, url: str, output_path: Path) -> Path:
        """
        Convierte el contenido de una URL a Markdown.

        Args:
            url: URL pública a convertir.
            output_path: Ruta donde se guardará el .md resultante.

        Returns:
            La ruta al archivo .md generado.
        """
        try:
            from markitdown import MarkItDown
        except ImportError as e:
            raise ImportError(
                "La librería 'markitdown' no está instalada. "
                "Instala con: pip install 'markitdown[pdf,docx,pptx,xlsx]'"
            ) from e

        try:
            md = MarkItDown()
            result = md.convert(url)
            text = result.text_content or ""
        except Exception as e:
            raise RuntimeError(f"Error al convertir URL a Markdown: {e}") from e

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return output_path
