from src.core.config import resolve_input_file, settings


def test_settings_paths():
    assert settings.STORAGE_DIR.exists()
    assert settings.INPUT_DIR.exists()
    assert settings.OUTPUT_DIR.exists()
    assert settings.DOCKER_COMPOSE_FILE.name == "docker-compose.yml"


def test_resolve_input_file_existing(tmp_path):
    dummy = settings.INPUT_DIR / "dummy_test.txt"
    dummy.write_text("hello")
    try:
        res = resolve_input_file("dummy_test.txt")
        assert res.exists()
        assert res.name == "dummy_test.txt"
    finally:
        if dummy.exists():
            dummy.unlink()
