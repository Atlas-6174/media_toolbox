from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.core.config import STANDARD_SUBDIRS, settings
from src.core.storage import ensure_default_directories, purge_storage
from src.main import app as cli_app
from src.web.app import app as web_app

client = TestClient(web_app)
runner = CliRunner()


def test_ensure_default_directories():
    """Verifica que ensure_default_directories cree todas las carpetas y .gitkeep."""
    ensure_default_directories()

    for sub in STANDARD_SUBDIRS:
        in_folder = settings.INPUT_DIR / sub
        out_folder = settings.OUTPUT_DIR / sub
        assert in_folder.is_dir()
        assert out_folder.is_dir()
        assert (in_folder / ".gitkeep").exists() or any(in_folder.iterdir())
        assert (out_folder / ".gitkeep").exists() or any(out_folder.iterdir())


def test_purge_storage_input_only():
    """Verifica que purgar solo input elimine archivos de datos pero conserve carpetas y output."""
    ensure_default_directories()

    test_in = settings.INPUT_DIR / "audios" / "test_input_sample.mp3"
    test_out = settings.OUTPUT_DIR / "audios" / "test_output_sample.mp3"
    test_in.write_bytes(b"sample input audio")
    test_out.write_bytes(b"sample output audio")

    try:
        res = purge_storage(target="input")
        assert res["status"] == "ok"
        assert res["deleted_count"] >= 1
        assert not test_in.exists()
        assert test_out.exists()  # Output no debe tocarse

        # Las carpetas clasificatorias deben seguir existiendo
        assert (settings.INPUT_DIR / "audios").is_dir()
        assert (settings.OUTPUT_DIR / "audios").is_dir()
    finally:
        if test_out.exists():
            test_out.unlink()


def test_purge_storage_output_only():
    """Verifica que purgar solo output elimine archivos de salida pero conserve carpetas e input."""
    ensure_default_directories()

    test_in = settings.INPUT_DIR / "videos" / "test_input_video.mp4"
    test_out = settings.OUTPUT_DIR / "videos" / "test_output_video.mp4"
    test_in.write_bytes(b"sample input video")
    test_out.write_bytes(b"sample output video")

    try:
        res = purge_storage(target="output")
        assert res["status"] == "ok"
        assert res["deleted_count"] >= 1
        assert not test_out.exists()
        assert test_in.exists()  # Input no debe tocarse

        # Las carpetas clasificatorias deben seguir existiendo
        assert (settings.INPUT_DIR / "videos").is_dir()
        assert (settings.OUTPUT_DIR / "videos").is_dir()
    finally:
        if test_in.exists():
            test_in.unlink()


def test_purge_storage_all():
    """Verifica que purgar todo elimine archivos de datos en input y output conservando carpetas."""
    ensure_default_directories()

    test_in = settings.INPUT_DIR / "pdfs" / "test_doc_in.pdf"
    test_out = settings.OUTPUT_DIR / "pdfs" / "test_doc_out.pdf"
    test_in.write_bytes(b"sample pdf input")
    test_out.write_bytes(b"sample pdf output")

    res = purge_storage(target="all")
    assert res["status"] == "ok"
    assert res["deleted_count"] >= 2
    assert not test_in.exists()
    assert not test_out.exists()

    # Verificar que las carpetas clasificatorias por defecto existen
    for sub in ["audios", "videos", "pdfs", "cmyk", "imagenes", "books"]:
        assert (settings.INPUT_DIR / sub).is_dir()
        assert (settings.OUTPUT_DIR / sub).is_dir()


def test_api_purge_storage_endpoints():
    """Verifica el endpoint POST /api/storage/purge para targets all, input y output."""
    ensure_default_directories()

    sample_in = settings.INPUT_DIR / "cmyk" / "sample_test_purge.svg"
    sample_out = settings.OUTPUT_DIR / "cmyk" / "sample_test_purge.pdf"
    sample_in.write_bytes(b"<svg></svg>")
    sample_out.write_bytes(b"%PDF-1.4")

    # Purga input
    res_input = client.post("/api/storage/purge?target=input")
    assert res_input.status_code == 200
    data_in = res_input.json()
    assert data_in["status"] == "ok"
    assert not sample_in.exists()
    assert sample_out.exists()

    # Purga output
    res_output = client.post("/api/storage/purge?target=output")
    assert res_output.status_code == 200
    data_out = res_output.json()
    assert data_out["status"] == "ok"
    assert not sample_out.exists()

    # Purga all
    res_all = client.post("/api/storage/purge?target=all")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["status"] == "ok"


def test_cli_purgar_command():
    """Verifica la ejecución del comando CLI media purgar y vaciar-cache."""
    # Test --help
    res_help = runner.invoke(cli_app, ["purgar", "--help"])
    assert res_help.exit_code == 0
    assert "Vacía" in res_help.output or "almacenamiento" in res_help.output

    # Test con --si
    res_run = runner.invoke(cli_app, ["purgar", "--si"])
    assert res_run.exit_code == 0
    assert "Almacenamiento vaciado" in res_run.output

    # Test cancelado
    res_cancel = runner.invoke(cli_app, ["purgar"], input="n\n")
    assert res_cancel.exit_code == 0
    assert "Operación cancelada" in res_cancel.output

    # Test alias vaciar-cache
    res_cache = runner.invoke(cli_app, ["vaciar-cache"])
    assert res_cache.exit_code == 0
    assert "Limpieza de caché completada" in res_cache.output
