import io
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.main import app as cli_app
from src.tools.downloader import DownloaderTool
from src.tools.image import ImageTool
from src.tools.pdf import PdfTool
from src.tools.privacy import PrivacyTool
from src.web.app import app as web_app

client = TestClient(web_app)
runner = CliRunner()


def test_privacy_tool_clean():
    """Verifica que PrivacyTool ejecute mat2 con los argumentos correctos."""
    tool = PrivacyTool()
    in_file = Path("storage/input/foto.jpg")
    out_file = Path("storage/output/limpios/foto.jpg")

    with patch("shutil.copy2"), patch("src.tools.privacy.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = ["Processing photo.jpg..."]
        tool.clean(in_file, out_file)
        assert mock_stream.called
        service_name, args = mock_stream.call_args[0]
        assert service_name == "privacy"
        assert "--inplace" in args


def test_privacy_tool_inspect():
    """Verifica que PrivacyTool parsee correctamente la salida de mat2 -s."""
    tool = PrivacyTool()
    in_file = Path("storage/input/foto.jpg")

    mock_output = [
        "[*] Mat2 analysis for photo.jpg\n",
        "  GPS: 40.7128 N, 74.0060 W\n",
        "  Camera: iPhone 13 Pro\n",
        "  Software: iOS 15.1\n",
    ]

    with patch("src.tools.privacy.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = mock_output
        meta = tool.inspect(in_file)
        assert mock_stream.called
        assert meta["GPS"] == "40.7128 N, 74.0060 W"
        assert meta["Camera"] == "iPhone 13 Pro"
        assert meta["Software"] == "iOS 15.1"


def test_pdf_compress():
    """Verifica que PdfTool.compress ejecute Ghostscript con el perfil seleccionado y resolución adecuada."""
    tool = PdfTool()
    in_file = Path("storage/input/doc.pdf")
    in_file.parent.mkdir(parents=True, exist_ok=True)
    in_file.write_bytes(b"test pdf content 1234567890")
    out_file = Path("storage/output/pdf_comprimidos/doc_comprimido.pdf")

    recorded_args = []

    def mock_run(svc, args):
        recorded_args.append((svc, args))
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"test pdf")

    with patch("src.tools.pdf.DockerRunner.run_service", side_effect=mock_run):
        result = tool.compress(in_file, out_file, perfil="screen")
        assert len(recorded_args) == 1
        service_name, args = recorded_args[0]
        assert service_name == "pdf"
        assert "-sDEVICE=pdfwrite" in args
        assert "-dPDFSETTINGS=/screen" in args
        assert "-dColorImageResolution=72" in args
        assert isinstance(result, dict)
        assert result["saved_pct"] > 0
        assert not result["was_already_optimal"]


def test_image_tool_heic():
    """Verifica que ImageTool ejecute heif-convert cuando la entrada es HEIC."""
    tool = ImageTool()
    in_file = Path("storage/input/IMG_1234.HEIC")
    out_file = Path("storage/output/imagenes/IMG_1234.jpg")

    with patch("src.tools.image.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = []
        tool.convert(in_file, out_file)
        assert mock_stream.called
        service_name, args = mock_stream.call_args[0]
        assert service_name == "tools"
        assert args[0] == "heif-convert"


def test_downloader_inspect():
    """Verifica que DownloaderTool.inspect parsee json de yt-dlp."""
    tool = DownloaderTool()
    mock_json = '{"title": "Video de Prueba", "duration": 185, "uploader": "Canal Oficial", "thumbnail": "https://img.youtube.com/vi/test/0.jpg"}'

    with patch("src.tools.downloader.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = [mock_json]
        data = tool.inspect("https://www.youtube.com/watch?v=test1234")
        assert data["title"] == "Video de Prueba"
        assert data["duration"] == 185
        assert data["duration_string"] == "3:05"
        assert data["uploader"] == "Canal Oficial"


def test_web_privacy_inspect_endpoint():
    """Verifica el endpoint POST /api/privacy/inspect."""
    with patch("src.tools.privacy.PrivacyTool.inspect", return_value={"Camera": "Sony A7III"}):
        file_content = b"fake image bytes"
        response = client.post(
            "/api/privacy/inspect",
            files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.jpg"
        assert data["metadata"]["Camera"] == "Sony A7III"


def test_web_privacy_clean_endpoint():
    """Verifica el endpoint POST /api/privacy/clean."""
    with patch("src.tools.privacy.PrivacyTool.clean"):
        file_content = b"fake image bytes"
        response = client.post(
            "/api/privacy/clean",
            files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data


def test_web_pdf_compress_endpoint():
    """Verifica el endpoint POST /api/pdf/compress."""
    with patch("src.tools.pdf.PdfTool.compress"):
        file_content = b"%PDF-1.4 fake pdf"
        response = client.post(
            "/api/pdf/compress",
            files={"file": ("doc.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"perfil": "screen"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data


def test_web_download_inspect_endpoint():
    """Verifica el endpoint POST /api/download/inspect."""
    with patch("src.tools.downloader.DownloaderTool.inspect", return_value={"title": "Test Video", "thumbnail": None}):
        response = client.post(
            "/api/download/inspect",
            data={"url": "https://www.youtube.com/watch?v=abc1234"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Video"


def test_web_batch_privacy_and_pdf_compress():
    """Verifica que el endpoint /api/batch/convert acepte tipo privacy y pdf_compress."""
    file1 = ("f1.pdf", io.BytesIO(b"%PDF-1.4 test 1"), "application/pdf")
    file2 = ("f2.pdf", io.BytesIO(b"%PDF-1.4 test 2"), "application/pdf")

    with patch("src.tools.pdf.PdfTool.compress"):
        response = client.post(
            "/api/batch/convert",
            files=[("files", file1), ("files", file2)],
            data={"tipo": "pdf_compress", "perfil": "ebook"},
        )
        assert response.status_code == 200
        assert "batch_id" in response.json()


def test_cli_commands():
    """Verifica que los nuevos comandos CLI de Typer estén registrados y respondan a --help."""
    res1 = runner.invoke(cli_app, ["pdf", "comprimir", "--help"])
    assert res1.exit_code == 0
    assert "Comprime y optimiza el tamaño de un archivo PDF" in res1.stdout

    res2 = runner.invoke(cli_app, ["limpiar", "--help"])
    assert res2.exit_code == 0
    assert "Elimina metadatos y rastros de privacidad usando MAT2" in res2.stdout

    res3 = runner.invoke(cli_app, ["privacidad", "--help"])
    assert res3.exit_code == 0
    assert "Elimina metadatos y rastros de privacidad" in res3.stdout
