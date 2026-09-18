"""
Tests para MarkdownTool y los endpoints /api/convert/markdown y /api/convert/markdown/url.
markitdown solo está disponible en el contenedor web (Python 3.11), por lo que todos
los tests mockean la librería externa usando `create=True` en el módulo markitdown.
"""

import io
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_markitdown_mock(text_content: str):
    """Crea un módulo markitdown falso con MarkItDown que retorna text_content."""
    mock_result = MagicMock()
    mock_result.text_content = text_content

    mock_md_instance = MagicMock()
    mock_md_instance.convert.return_value = mock_result

    MockMarkItDown = MagicMock(return_value=mock_md_instance)

    fake_module = types.ModuleType("markitdown")
    fake_module.MarkItDown = MockMarkItDown
    return fake_module, MockMarkItDown


# ---------------------------------------------------------------------------
# Tests unitarios de MarkdownTool
# ---------------------------------------------------------------------------


class TestMarkdownTool:
    """Tests para src/tools/markdown_tool.py"""

    def test_convert_success(self, tmp_path):
        """Conversión exitosa: mockea MarkItDown y verifica el archivo .md generado."""
        from src.tools.markdown_tool import MarkdownTool

        input_file = tmp_path / "test.pdf"
        input_file.write_bytes(b"%PDF-1.4 fake content")
        output_file = tmp_path / "test.md"

        fake_module, _ = _make_markitdown_mock("# Título\n\nContenido de prueba.")

        with patch.dict(sys.modules, {"markitdown": fake_module}):
            result = MarkdownTool().convert(input_file, output_file)

        assert result == output_file
        assert output_file.read_text(encoding="utf-8") == "# Título\n\nContenido de prueba."

    def test_convert_file_not_found(self, tmp_path):
        """Debe lanzar ValueError si el archivo de entrada no existe."""
        from src.tools.markdown_tool import MarkdownTool

        fake_module, _ = _make_markitdown_mock("")
        with patch.dict(sys.modules, {"markitdown": fake_module}):
            with pytest.raises(ValueError, match="no existe"):
                MarkdownTool().convert(tmp_path / "nonexistent.pdf", tmp_path / "out.md")

    def test_convert_unsupported_extension(self, tmp_path):
        """Debe lanzar ValueError para extensiones no soportadas."""
        from src.tools.markdown_tool import MarkdownTool

        f = tmp_path / "video.mp4"
        f.write_bytes(b"fake")

        fake_module, _ = _make_markitdown_mock("")
        with patch.dict(sys.modules, {"markitdown": fake_module}):
            with pytest.raises(ValueError, match="no soportada"):
                MarkdownTool().convert(f, tmp_path / "out.md")

    def test_convert_markitdown_import_error(self, tmp_path):
        """Debe lanzar ImportError si markitdown no está instalado."""
        from src.tools.markdown_tool import MarkdownTool

        input_file = tmp_path / "doc.docx"
        input_file.write_bytes(b"PK fake docx")

        with patch.dict(sys.modules, {"markitdown": None}):
            with pytest.raises((ImportError, SystemError)):
                MarkdownTool().convert(input_file, tmp_path / "out.md")

    def test_supported_extensions_list(self):
        """Verifica que las extensiones clave estén en la lista de soportadas."""
        from src.tools.markdown_tool import MarkdownTool

        exts = MarkdownTool.SUPPORTED_EXTENSIONS
        for ext in [".pdf", ".docx", ".pptx", ".xlsx", ".html", ".csv", ".epub", ".txt"]:
            assert ext in exts, f"Extensión {ext} debería estar soportada"

    def test_convert_url_success(self, tmp_path):
        """Conversión de URL exitosa usando convert_url."""
        from src.tools.markdown_tool import MarkdownTool

        output_file = tmp_path / "page.md"
        fake_module, _ = _make_markitdown_mock("# Página Web\n\nContenido extraído.")

        with patch.dict(sys.modules, {"markitdown": fake_module}):
            result = MarkdownTool().convert_url("https://example.com", output_file)

        assert result == output_file
        assert "Página Web" in output_file.read_text(encoding="utf-8")

    def test_convert_creates_output_directory(self, tmp_path):
        """La conversión debe crear el directorio de salida si no existe."""
        from src.tools.markdown_tool import MarkdownTool

        input_file = tmp_path / "doc.txt"
        input_file.write_text("Hola mundo")
        output_file = tmp_path / "nested" / "deep" / "doc.md"

        fake_module, _ = _make_markitdown_mock("Hola mundo")
        with patch.dict(sys.modules, {"markitdown": fake_module}):
            MarkdownTool().convert(input_file, output_file)

        assert output_file.exists()


# ---------------------------------------------------------------------------
# Tests de los endpoints de la API
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Cliente de prueba FastAPI."""
    from fastapi.testclient import TestClient

    from src.web.app import app

    return TestClient(app)


class TestMarkdownAPIEndpoint:
    """Tests para POST /api/convert/markdown"""

    def test_convert_pdf_success(self, client):
        """Conversión de PDF exitosa devuelve markdown y metadatos."""
        fake_module, _ = _make_markitdown_mock("# Documento\n\nContenido del PDF.")

        with patch.dict(sys.modules, {"markitdown": fake_module}):
            response = client.post(
                "/api/convert/markdown",
                files={"file": ("documento.pdf", io.BytesIO(b"%PDF fake"), "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert "markdown" in data
        assert data["char_count"] > 0
        assert data["download_url"].endswith(".md")

    def test_convert_unsupported_format_returns_415(self, client):
        """Formato no soportado debe retornar HTTP 415."""
        response = client.post(
            "/api/convert/markdown",
            files={"file": ("video.mp4", io.BytesIO(b"fake"), "video/mp4")},
        )
        assert response.status_code == 415

    def test_convert_docx_success(self, client):
        """Conversión de DOCX devuelve Markdown válido."""
        fake_module, _ = _make_markitdown_mock("## Sección\n\nTexto del documento Word.")

        with patch.dict(sys.modules, {"markitdown": fake_module}):
            response = client.post(
                "/api/convert/markdown",
                files={
                    "file": (
                        "informe.docx",
                        io.BytesIO(b"PK fake"),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )

        assert response.status_code == 200
        assert "## Sección" in response.json()["markdown"]

    def test_convert_url_endpoint_success(self, client):
        """Conversión de URL devuelve Markdown de la página."""
        fake_module, _ = _make_markitdown_mock("# Web Page\n\nContenido de ejemplo.")

        with patch.dict(sys.modules, {"markitdown": fake_module}):
            response = client.post(
                "/api/convert/markdown/url",
                data={"url": "https://example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source_url"] == "https://example.com"
        assert "# Web Page" in data["markdown"]

    def test_convert_url_invalid_scheme_returns_400(self, client):
        """URLs sin http/https deben devolver HTTP 400."""
        response = client.post(
            "/api/convert/markdown/url",
            data={"url": "ftp://ejemplo.com"},
        )
        assert response.status_code == 400

    def test_convert_line_count_metadata(self, client):
        """El conteo de líneas en la respuesta es correcto."""
        fake_module, _ = _make_markitdown_mock("Línea 1\nLínea 2\nLínea 3")

        with patch.dict(sys.modules, {"markitdown": fake_module}):
            response = client.post(
                "/api/convert/markdown",
                files={"file": ("data.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
            )

        assert response.status_code == 200
        assert response.json()["line_count"] == 3
