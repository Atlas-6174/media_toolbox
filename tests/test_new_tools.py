import io
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.main import app as cli_app
from src.tools.ffmpeg import FFmpegTool
from src.tools.image import ImageTool
from src.tools.office import OfficeTool
from src.tools.pdf import PdfTool
from src.tools.rembg_tool import RembgTool
from src.web.app import app as web_app

client = TestClient(web_app)
runner = CliRunner()


# ---------------------------------------------------------------------------
# PDF: rotar / proteger / desde-office
# ---------------------------------------------------------------------------


def test_pdf_tool_rotate():
    tool = PdfTool()
    with patch("src.tools.pdf.DockerRunner.run_service") as mock_run:
        tool.rotate(Path("storage/input/doc.pdf"), Path("storage/output/pdfs/doc_rotado.pdf"), angulo=90, paginas="1-3")
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "pdf"
        assert "qpdf" in args
        assert "--rotate=+90:1-3" in args


def test_pdf_tool_protect():
    tool = PdfTool()
    with patch("src.tools.pdf.DockerRunner.run_service") as mock_run:
        tool.protect(Path("storage/input/doc.pdf"), Path("storage/output/pdfs/doc_prot.pdf"), password_usuario="clave123")
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "pdf"
        assert "--encrypt" in args
        assert "clave123" in args
        assert "256" in args


def test_office_tool_convert_to_pdf(tmp_path):
    tool = OfficeTool()
    in_file = tmp_path / "doc.docx"
    in_file.write_bytes(b"dummy")
    out_file = tmp_path / "doc.pdf"
    generated = tmp_path / "doc.pdf"  # LibreOffice generaría el mismo stem que el input

    with patch("src.tools.office.DockerRunner.run_service") as mock_run:
        def fake_run(service, args):
            generated.write_bytes(b"%PDF-1.4 fake")

        mock_run.side_effect = fake_run
        tool.convert_to_pdf(in_file, out_file)
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "libreoffice"
        assert "--convert-to" in args
        assert "pdf" in args
        assert out_file.exists()


def test_api_pdf_rotate_and_protect_endpoints():
    dummy_pdf = io.BytesIO(b"%PDF-1.4 dummy pdf content")

    with patch("src.web.app.PdfTool.rotate"), patch("src.web.app.PdfTool.protect"):
        res_rot = client.post(
            "/api/pdf/rotate",
            files={"file": ("doc.pdf", dummy_pdf, "application/pdf")},
            data={"angulo": 90, "paginas": "1-z"},
        )
        assert res_rot.status_code == 200
        assert "task_id" in res_rot.json()

        dummy_pdf.seek(0)
        res_prot = client.post(
            "/api/pdf/protect",
            files={"file": ("doc.pdf", dummy_pdf, "application/pdf")},
            data={"password": "clave123"},
        )
        assert res_prot.status_code == 200
        assert "task_id" in res_prot.json()


def test_api_office_to_pdf_endpoint_rejects_unsupported_extension():
    res = client.post(
        "/api/pdf/from-office",
        files={"file": ("archivo.exe", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert res.status_code == 415


def test_api_office_to_pdf_endpoint_accepts_docx():
    with patch("src.web.app.OfficeTool.convert_to_pdf"):
        res = client.post(
            "/api/pdf/from-office",
            files={"file": ("doc.docx", io.BytesIO(b"dummy docx"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert res.status_code == 200
        assert "task_id" in res.json()


# ---------------------------------------------------------------------------
# Subtítulos
# ---------------------------------------------------------------------------


def test_ffmpeg_tool_extract_subtitles():
    tool = FFmpegTool()
    with patch("src.tools.ffmpeg.DockerRunner.run_service") as mock_run:
        tool.extract_subtitles(Path("storage/input/videos/v.mp4"), Path("storage/output/subtitulos/v.srt"), pista=1)
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "ffmpeg"
        assert "-map" in args
        assert "0:s:1" in args


def test_ffmpeg_tool_burn_subtitles():
    tool = FFmpegTool()
    with patch("src.tools.ffmpeg.DockerRunner.run_service") as mock_run:
        tool.burn_subtitles(
            Path("storage/input/videos/v.mp4"), Path("storage/input/videos/v.srt"), Path("storage/output/marcas_agua/v_sub.mp4")
        )
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "ffmpeg"
        assert any(a.startswith("subtitles=") for a in args)


def test_api_subtitles_endpoints():
    dummy_video = io.BytesIO(b"dummy video content")

    with patch("src.web.app.FFmpegTool.extract_subtitles"):
        res_ext = client.post(
            "/api/subtitles/extract",
            files={"file": ("video.mp4", dummy_video, "video/mp4")},
            data={"pista": 0},
        )
        assert res_ext.status_code == 200
        assert "task_id" in res_ext.json()

    with patch("src.web.app.FFmpegTool.burn_subtitles"):
        dummy_video.seek(0)
        res_burn = client.post(
            "/api/subtitles/burn",
            files={
                "file": ("video.mp4", dummy_video, "video/mp4"),
                "subtitle_file": ("subs.srt", io.BytesIO(b"1\n00:00:00,000 --> 00:00:01,000\nHola\n"), "text/plain"),
            },
        )
        assert res_burn.status_code == 200
        assert "task_id" in res_burn.json()


# ---------------------------------------------------------------------------
# Marca de agua
# ---------------------------------------------------------------------------


def test_image_tool_watermark_text():
    tool = ImageTool()
    with patch("src.tools.image.DockerRunner.run_service") as mock_run:
        tool.watermark(Path("storage/input/imagenes/foto.jpg"), Path("storage/output/marcas_agua/foto_wm.jpg"), texto="Hola")
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "tools"
        assert "convert" in args
        assert "Hola" in args


def test_image_tool_watermark_logo():
    tool = ImageTool()
    with patch("src.tools.image.DockerRunner.run_service") as mock_run:
        tool.watermark(
            Path("storage/input/imagenes/foto.jpg"),
            Path("storage/output/marcas_agua/foto_wm.jpg"),
            logo_file=Path("storage/input/imagenes/logo.png"),
        )
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "tools"
        assert "composite" in args


def test_ffmpeg_tool_watermark_video_text_and_logo():
    tool = FFmpegTool()
    with patch("src.tools.ffmpeg.DockerRunner.run_service") as mock_run:
        tool.watermark(Path("storage/input/videos/v.mp4"), Path("storage/output/marcas_agua/v_wm.mp4"), texto="Hola")
        service, args = mock_run.call_args[0]
        assert any("drawtext=" in a for a in args)

    with patch("src.tools.ffmpeg.DockerRunner.run_service") as mock_run:
        tool.watermark(
            Path("storage/input/videos/v.mp4"),
            Path("storage/output/marcas_agua/v_wm.mp4"),
            logo_file=Path("storage/input/imagenes/logo.png"),
        )
        service, args = mock_run.call_args[0]
        assert any("overlay=" in a for a in args)


def test_api_watermark_endpoints():
    dummy_img = io.BytesIO(b"dummy image data")
    dummy_video = io.BytesIO(b"dummy video data")

    with patch("src.web.app.ImageTool.watermark"):
        res_img = client.post(
            "/api/watermark/image",
            files={"file": ("foto.jpg", dummy_img, "image/jpeg")},
            data={"texto": "Marca"},
        )
        assert res_img.status_code == 200
        assert "task_id" in res_img.json()

    with patch("src.web.app.FFmpegTool.watermark"):
        res_video = client.post(
            "/api/watermark/video",
            files={"file": ("video.mp4", dummy_video, "video/mp4")},
            data={"texto": "Marca"},
        )
        assert res_video.status_code == 200
        assert "task_id" in res_video.json()


# ---------------------------------------------------------------------------
# Quitar fondo
# ---------------------------------------------------------------------------


def test_rembg_tool_remove_background():
    tool = RembgTool()
    with patch("src.tools.rembg_tool.DockerRunner.run_service") as mock_run:
        tool.remove_background(Path("storage/input/imagenes/foto.png"), Path("storage/output/sin_fondo/foto.png"))
        assert mock_run.called
        service, args = mock_run.call_args[0]
        assert service == "rembg"
        assert "i" in args
        assert "-m" in args
        assert "u2net" in args


def test_api_remove_background_endpoint():
    dummy_img = io.BytesIO(b"dummy image data")
    with patch("src.web.app.RembgTool.remove_background"):
        res = client.post(
            "/api/image/remove-background",
            files={"file": ("foto.png", dummy_img, "image/png")},
        )
        assert res.status_code == 200
        assert "task_id" in res.json()


# ---------------------------------------------------------------------------
# CLI: nuevos comandos registrados
# ---------------------------------------------------------------------------


def test_cli_new_feature_commands_registered():
    for args, expect in [
        (["pdf", "rotar", "--help"], "angulo"),
        (["pdf", "proteger", "--help"], "password"),
        (["pdf", "desde-office", "--help"], "LibreOffice"),
        (["subtitulos", "extraer", "--help"], "pista"),
        (["subtitulos", "quemar", "--help"], "subtitulo"),
        (["marca-agua", "--help"], "posicion"),
        (["quitar-fondo", "--help"], "fondo"),
    ]:
        res = runner.invoke(cli_app, args)
        assert res.exit_code == 0, res.output
        assert expect.lower() in res.output.lower()
