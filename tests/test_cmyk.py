import io
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.main import app as cli_app
from src.tools.cmyk import CmykTool
from src.web.app import app as web_app

client = TestClient(web_app)
runner = CliRunner()


def test_cmyk_tool_svg_to_pdf():
    """Verifica que CmykTool invoque Inkscape para SVG y luego Ghostscript para PDF CMYK."""
    tool = CmykTool()
    in_file = Path("storage/input/ilustracion.svg")
    out_file = Path("storage/output/cmyk/ilustracion_cmyk.pdf")

    calls = []

    def mock_run_service(service, args):
        calls.append((service, args))

    with patch("src.tools.cmyk.DockerRunner.run_service", side_effect=mock_run_service):
        tool.convert(in_file, out_file, formato="pdf", perfil="fogra39")

        assert len(calls) == 2
        # Llamada 1: Inkscape
        svc1, args1 = calls[0]
        assert svc1 == "cmyk"
        assert args1[0] == "inkscape"
        assert "--export-area-page" in args1

        # Llamada 2: Ghostscript CMYK
        svc2, args2 = calls[1]
        assert svc2 == "cmyk"
        assert args2[0] == "gs"
        assert "-sDEVICE=pdfwrite" in args2
        assert "-sColorConversionStrategy=CMYK" in args2
        assert "-dProcessColorModel=/DeviceCMYK" in args2


def test_cmyk_tool_pdf_to_tiff():
    """Verifica que un PDF se convierta directamente a TIFF 300 DPI CMYK usando Ghostscript."""
    tool = CmykTool()
    in_file = Path("storage/input/diseno.pdf")
    out_file = Path("storage/output/cmyk/diseno_cmyk.tif")

    calls = []

    def mock_run_service(service, args):
        calls.append((service, args))

    with patch("src.tools.cmyk.DockerRunner.run_service", side_effect=mock_run_service):
        tool.convert(in_file, out_file, formato="tiff", dpi=300)

        assert len(calls) == 1
        svc, args = calls[0]
        assert svc == "cmyk"
        assert args[0] == "gs"
        assert "-sDEVICE=tiff32nc" in args
        assert "-r300" in args


def test_cmyk_tool_raster_image():
    """Verifica que una imagen PNG/JPG se convierta a CMYK usando ImageMagick."""
    tool = CmykTool()
    in_file = Path("storage/input/foto.png")
    out_file = Path("storage/output/cmyk/foto_cmyk.jpg")

    calls = []

    def mock_run_service(service, args):
        calls.append((service, args))

    with patch("src.tools.cmyk.DockerRunner.run_service", side_effect=mock_run_service):
        tool.convert(in_file, out_file, formato="jpg", dpi=300)

        assert len(calls) == 1
        svc, args = calls[0]
        assert svc == "cmyk"
        assert args[0] == "convert"
        assert "-colorspace" in args
        assert "CMYK" in args


def test_web_cmyk_endpoint():
    """Verifica el endpoint POST /api/cmyk/convert."""
    with patch("src.tools.cmyk.CmykTool.convert"):
        svg_content = b"<svg><circle cx='50' cy='50' r='40'/></svg>"
        response = client.post(
            "/api/cmyk/convert",
            files={"file": ("dibujo.svg", io.BytesIO(svg_content), "image/svg+xml")},
            data={"formato": "pdf", "perfil": "fogra39", "dpi": "300"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data


def test_web_batch_cmyk_endpoint():
    """Verifica el endpoint POST /api/batch/convert con tipo cmyk."""
    with patch("src.tools.cmyk.CmykTool.convert"):
        file1 = ("i1.svg", io.BytesIO(b"<svg>1</svg>"), "image/svg+xml")
        file2 = ("i2.svg", io.BytesIO(b"<svg>2</svg>"), "image/svg+xml")
        response = client.post(
            "/api/batch/convert",
            files=[("files", file1), ("files", file2)],
            data={"tipo": "cmyk", "formato": "pdf", "perfil": "fogra39"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "batch_id" in data


def test_cli_cmyk_commands():
    """Verifica los comandos CLI cmyk e imprenta."""
    res1 = runner.invoke(cli_app, ["cmyk", "--help"])
    assert res1.exit_code == 0
    assert "Convierte ilustraciones y diseños de RGB a CMYK puro" in res1.stdout

    res2 = runner.invoke(cli_app, ["imprenta", "--help"])
    assert res2.exit_code == 0
    assert "Convierte ilustraciones y diseños de RGB a CMYK puro" in res2.stdout
