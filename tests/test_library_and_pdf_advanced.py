import io
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.main import app as cli_app
from src.tools.ffmpeg import FFmpegTool
from src.tools.pdf import PdfTool
from src.web.app import app as web_app

client = TestClient(web_app)
runner = CliRunner()


def test_pdf_tool_ocr():
    """Verifica que PdfTool.ocr invoque ocrmypdf con el idioma y opciones correctas."""
    tool = PdfTool()
    in_file = Path("storage/input/escaneado.pdf")
    out_file = Path("storage/output/pdf_ocr/escaneado_ocr.pdf")

    with patch("src.tools.pdf.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = ["Running OCR..."]
        tool.ocr(in_file, out_file, idioma="spa+eng")
        assert mock_stream.called
        service, args = mock_stream.call_args[0]
        assert service == "pdf"
        assert "ocrmypdf" in args
        assert "-l" in args
        assert "spa+eng" in args
        assert "--skip-text" in args


def test_pdf_tool_extract_pages():
    """Verifica que PdfTool.extract_pages use qpdf con el rango de páginas adecuado."""
    tool = PdfTool()
    in_file = Path("storage/input/doc.pdf")
    out_file = Path("storage/output/pdf_paginas/doc_p1-3.pdf")

    with patch("src.tools.pdf.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = ["Extracting pages..."]
        tool.extract_pages(in_file, out_file, paginas="1-3")
        assert mock_stream.called
        service, args = mock_stream.call_args[0]
        assert service == "pdf"
        assert "qpdf" in args
        assert "--pages" in args
        assert "1-3" in args


def test_pdf_tool_to_images(tmp_path):
    """Verifica que PdfTool.pdf_to_images use pdftoppm con formato y DPI correctos."""
    tool = PdfTool()
    in_file = Path("storage/input/doc.pdf")
    out_dir = tmp_path / "images_out"

    with patch("src.tools.pdf.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = ["Rendering pages..."]
        tool.pdf_to_images(in_file, out_dir, formato="png", dpi=300)
        assert mock_stream.called
        service, args = mock_stream.call_args[0]
        assert service == "pdf"
        assert "pdftoppm" in args
        assert "-png" in args
        assert "-r" in args
        assert "300" in args


def test_ffmpeg_change_speed():
    """Verifica que FFmpegTool.change_speed use el filtro atempo para no alterar el tono."""
    tool = FFmpegTool()
    in_file = Path("storage/input/audio.mp3")
    out_file = Path("storage/output/audio/audio_1.5x.mp3")

    with patch("src.tools.ffmpeg.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = ["frame= 100..."]
        tool.change_speed(in_file, out_file, velocidad=1.5)
        assert mock_stream.called
        service, args = mock_stream.call_args[0]
        assert service == "ffmpeg"
        assert "-filter:a" in args
        assert any("atempo=" in a for a in args)


def test_api_library_and_delete():
    """Verifica el listado de biblioteca GET /api/library y eliminación DELETE /api/library/{category}/{filename}."""
    test_out = Path("storage/output/audio")
    test_out.mkdir(parents=True, exist_ok=True)
    sample_file = test_out / "test_sample_audio.mp3"
    sample_file.write_bytes(b"dummy audio content")

    try:
        # GET /api/library
        res = client.get("/api/library")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert any(f["filename"] == "test_sample_audio.mp3" and f["category"] == "audio" for f in data["items"])

        # DELETE /api/library/audio/test_sample_audio.mp3
        del_res = client.delete("/api/library/audio/test_sample_audio.mp3")
        assert del_res.status_code == 200
        assert not sample_file.exists()

        # DELETE inexistente -> 404
        del_res_404 = client.delete("/api/library/audio/no_existe.mp3")
        assert del_res_404.status_code == 404
    finally:
        if sample_file.exists():
            sample_file.unlink()


def test_api_storage_info_and_clean_temp():
    """Verifica GET /api/storage/info y POST /api/storage/clean-temp."""
    temp_dir = Path("storage/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / "junk_temp_test.tmp"
    temp_file.write_bytes(b"junk")

    try:
        info_res = client.get("/api/storage/info")
        assert info_res.status_code == 200
        info_data = info_res.json()
        assert "output_human" in info_data
        assert "temp_human" in info_data
        assert "output_files_count" in info_data

        clean_res = client.post("/api/storage/clean-temp")
        assert clean_res.status_code == 200
        assert not temp_file.exists()
    finally:
        if temp_file.exists():
            temp_file.unlink()


def test_api_pdf_advanced_endpoints():
    """Verifica que los endpoints de PDF OCR, extracción y PDF a imágenes encolen tareas."""
    dummy_pdf = io.BytesIO(b"%PDF-1.4 dummy pdf content")

    with patch("src.web.app.PdfTool.ocr"), patch("src.web.app.PdfTool.extract_pages"), patch("src.web.app.PdfTool.pdf_to_images"):
        # OCR
        res_ocr = client.post(
            "/api/pdf/ocr",
            files={"file": ("doc.pdf", dummy_pdf, "application/pdf")},
            data={"idioma": "spa+eng"},
        )
        assert res_ocr.status_code == 200
        assert "task_id" in res_ocr.json()

        # Extraer páginas
        dummy_pdf.seek(0)
        res_ext = client.post(
            "/api/pdf/extract-pages",
            files={"file": ("doc.pdf", dummy_pdf, "application/pdf")},
            data={"paginas": "1-3"},
        )
        assert res_ext.status_code == 200
        assert "task_id" in res_ext.json()

        # PDF a imágenes
        dummy_pdf.seek(0)
        res_img = client.post(
            "/api/pdf/to-images",
            files={"file": ("doc.pdf", dummy_pdf, "application/pdf")},
            data={"formato": "png", "dpi": 300},
        )
        assert res_img.status_code == 200
        assert "task_id" in res_img.json()


def test_api_audio_speed_endpoint():
    """Verifica que POST /api/audio/speed encole la tarea correctamente."""
    dummy_audio = io.BytesIO(b"dummy mp3 data")

    with patch("src.web.app.FFmpegTool.change_speed"):
        res = client.post(
            "/api/audio/speed",
            files={"file": ("sample.mp3", dummy_audio, "audio/mpeg")},
            data={"velocidad": 1.25},
        )
        assert res.status_code == 200
        assert "task_id" in res.json()


def test_cli_new_commands():
    """Verifica que los nuevos comandos de CLI estén registrados y respondan a --help."""
    res_ocr = runner.invoke(cli_app, ["pdf", "ocr", "--help"])
    assert res_ocr.exit_code == 0
    assert "OCR" in res_ocr.output

    res_ext = runner.invoke(cli_app, ["pdf", "extraer", "--help"])
    assert res_ext.exit_code == 0
    assert "paginas" in res_ext.output

    res_img = runner.invoke(cli_app, ["pdf", "imagenes", "--help"])
    assert res_img.exit_code == 0
    assert "dpi" in res_img.output

    res_spd = runner.invoke(cli_app, ["velocidad", "--help"])
    assert res_spd.exit_code == 0
    assert "velocidad" in res_spd.output

    res_lib = runner.invoke(cli_app, ["biblioteca"])
    assert res_lib.exit_code == 0

    res_clean = runner.invoke(cli_app, ["limpiar-temp"])
    assert res_clean.exit_code == 0
