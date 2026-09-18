import logging
from contextlib import contextmanager
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.logging_config import LOG_FILE, setup_logging
from src.web.app import app, mark_task_error, resolve_safe_path, safe_filename, tasks

client = TestClient(app)


def test_web_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "MediaBox" in response.text
    assert "Extraer Audio" in response.text
    assert "notif-toggle" in response.text
    assert "toast-container" in response.text


def test_web_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "docker" in data
    assert "storage" in data
    assert "input" in data["storage"]
    assert "output" in data["storage"]


def test_web_static_manifest():
    response = client.get("/static/manifest.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "MediaBox"


def test_safe_filename_strips_directory_components():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("a/b/c.txt") == "c.txt"


def test_safe_filename_rejects_dot_segments():
    assert safe_filename(".") not in (".", "")
    assert safe_filename("..") not in ("..", "")
    assert safe_filename(None) != ""


def test_resolve_safe_path_confines_result_to_base_dir():
    base = settings.OUTPUT_DIR.resolve()
    result = resolve_safe_path(settings.OUTPUT_DIR, "..", "secret.txt")
    assert result == base or base in result.parents


def test_resolve_safe_path_accepts_normal_subpaths():
    result = resolve_safe_path(settings.INPUT_DIR, "videos", "clip.mp4")
    assert settings.INPUT_DIR.resolve() in result.parents
    assert result.name == "clip.mp4"


def test_download_output_file_404_for_missing_file_no_traversal():
    response = client.get("/api/files/pdfs/does-not-exist.pdf")
    assert response.status_code == 404


def test_preview_output_file_404_for_missing_file():
    response = client.get("/api/preview/pdfs/does-not-exist.pdf")
    assert response.status_code == 404


def test_preview_output_file_serves_inline():
    out_dir = settings.OUTPUT_DIR / "imagenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    sample = out_dir / "preview_test_sample.txt"
    sample.write_text("hola")
    try:
        response = client.get(f"/api/preview/imagenes/{sample.name}")
        assert response.status_code == 200
        assert response.headers["content-disposition"].startswith("inline")
    finally:
        sample.unlink(missing_ok=True)


def test_download_output_file_forces_attachment():
    out_dir = settings.OUTPUT_DIR / "imagenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    sample = out_dir / "download_test_sample.txt"
    sample.write_text("hola")
    try:
        response = client.get(f"/api/files/imagenes/{sample.name}")
        assert response.status_code == 200
        assert response.headers["content-disposition"].startswith("attachment")
    finally:
        sample.unlink(missing_ok=True)


def test_cors_does_not_allow_wildcard_with_credentials():
    response = client.options(
        "/api/status",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-credentials") != "true"


@contextmanager
def _capture_mediabox_logs():
    """El logger 'mediabox' tiene propagate=False (evita duplicar logs en producción),
    así que `caplog` de pytest (que escucha en el logger raíz) no lo detecta.
    Este helper adjunta un handler directamente al logger para poder inspeccionarlo en tests."""
    records = []

    class _ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _ListHandler()
    mediabox_logger = logging.getLogger("mediabox")
    mediabox_logger.addHandler(handler)
    try:
        yield records
    finally:
        mediabox_logger.removeHandler(handler)


def test_setup_logging_is_idempotent():
    logger_a = setup_logging()
    logger_b = setup_logging()
    assert logger_a is logger_b
    assert len(logger_a.handlers) == 2


def test_mark_task_error_logs_and_updates_task():
    task_id = "test-task-error"
    tasks[task_id] = {"status": "running"}
    try:
        with _capture_mediabox_logs() as records:
            mark_task_error(task_id, RuntimeError("boom"))
        assert tasks[task_id] == {"status": "error", "message": "boom"}
        assert any("terminó con error" in rec.getMessage() for rec in records)
    finally:
        tasks.pop(task_id, None)


def test_log_unhandled_exceptions_middleware_logs_and_reraises():
    import asyncio

    from src.web.app import log_unhandled_exceptions

    fake_request = MagicMock()
    fake_request.method = "GET"
    fake_request.url.path = "/api/whatever"

    async def call_next(request):
        raise RuntimeError("kaboom")

    async def run():
        try:
            await log_unhandled_exceptions(fake_request, call_next)
        except RuntimeError:
            return True
        return False

    with _capture_mediabox_logs() as records:
        raised = asyncio.run(run())

    assert raised is True
    assert any("Error no manejado" in rec.getMessage() for rec in records)


def test_log_file_created_after_logging():
    setup_logging()
    assert LOG_FILE.parent.exists()
