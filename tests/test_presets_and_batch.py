import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.core.notify import notify, open_directory
from src.tools.compressor import VideoCompressorTool
from src.tools.ffmpeg import FFmpegTool
from src.web.app import app, batches

client = TestClient(app)


def test_notify_and_open_directory():
    """Verifica que notify y open_directory manejen las llamadas de forma segura."""
    with patch("subprocess.run") as mock_run:
        notify("Test", "Mensaje de prueba")
        open_directory(Path("."))
        assert mock_run.called


def test_video_compressor_presets():
    """Verifica que los perfiles 'whatsapp' y 'vertical_reels' generen los parámetros adecuados."""
    compressor = VideoCompressorTool()
    in_file = Path("storage/input/video.mp4")
    out_file = Path("storage/output/comprimidos/video.mp4")

    with patch("src.tools.compressor.DockerRunner.run_service_stream", return_value=[]):
        # WhatsApp preset
        compressor.compress(in_file, out_file, perfil="whatsapp")

        # Vertical Reels preset
        compressor.compress(in_file, out_file, perfil="vertical_reels")


def test_ffmpeg_loudnorm_preset():
    """Verifica que FFmpegTool incluya el filtro loudnorm cuando normalizar=True."""
    tool = FFmpegTool()
    in_file = Path("storage/input/audio.mp4")
    out_file = Path("storage/output/audios/audio.mp3")

    with patch("src.tools.ffmpeg.DockerRunner.run_service_stream") as mock_stream:
        mock_stream.return_value = []
        tool.convert(in_file, out_file, normalizar=True)
        assert mock_stream.called
        args = mock_stream.call_args[0][1]
        assert "-af" in args
        assert any("loudnorm" in arg for arg in args)


def test_batch_convert_and_zip_download(tmp_path):
    """Verifica la creación y descarga de un lote en formato ZIP."""
    batch_id = "test-batch-1234"
    dummy_file1 = tmp_path / "salida1.mp3"
    dummy_file2 = tmp_path / "salida2.mp3"
    dummy_file1.write_text("audio 1 content")
    dummy_file2.write_text("audio 2 content")

    # Crear zip de prueba
    zip_path = tmp_path / "lote_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(dummy_file1, arcname="salida1.mp3")
        zf.write(dummy_file2, arcname="salida2.mp3")

    batches[batch_id] = {
        "id": batch_id,
        "status": "done",
        "total": 2,
        "completed": 2,
        "failed": 0,
        "zip_path": str(zip_path),
        "download_zip": f"/api/batch/download/{batch_id}",
    }

    # Verificar estado del lote
    res_status = client.get(f"/api/batch/{batch_id}")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["status"] == "done"
    assert data["percent"] == 100

    # Verificar descarga del ZIP
    res_dl = client.get(f"/api/batch/download/{batch_id}")
    assert res_dl.status_code == 200
    assert res_dl.headers["content-type"] == "application/zip"

    # Verificar contenido del zip
    with zipfile.ZipFile(io.BytesIO(res_dl.content)) as zf:
        names = zf.namelist()
        assert "salida1.mp3" in names
        assert "salida2.mp3" in names
