from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from src.main import app, select_files_or_all, select_single_file

runner = CliRunner()


def test_cli_help():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "Media Toolbox" in res.stdout
    assert "convertir" in res.stdout
    assert "audio" in res.stdout
    assert "descargar" in res.stdout
    assert "recortar" in res.stdout
    assert "gif" in res.stdout
    assert "comprimir" in res.stdout
    assert "imagen" in res.stdout
    assert "pdf" in res.stdout
    assert "estado" in res.stdout


def test_cli_pdf_help():
    res = runner.invoke(app, ["pdf", "--help"])
    assert res.exit_code == 0
    assert "unir" in res.stdout


def test_select_single_file_returns_none_on_empty_candidates(capsys):
    result = select_single_file(None, [], "cosas", "No hay cosas disponibles.")
    assert result is None
    assert "No hay cosas disponibles." in capsys.readouterr().out


def test_select_single_file_resolves_direct_argument():
    with patch("src.main.resolve_input_file", return_value=Path("storage/input/clip.mp4")) as mock_resolve:
        result = select_single_file("clip.mp4", [], "videos", "sin archivos")
    mock_resolve.assert_called_once_with("clip.mp4", None, subfolder="")
    assert result == Path("storage/input/clip.mp4")


def _make_candidates(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    return [a, b]


def test_select_single_file_rejects_zero_instead_of_wrapping_to_last(tmp_path):
    candidates = _make_candidates(tmp_path)
    with patch("src.main.Prompt.ask", return_value="0"):
        result = select_single_file(None, candidates, "videos", "sin archivos")
    assert result is None


def test_select_single_file_accepts_valid_index(tmp_path):
    candidates = _make_candidates(tmp_path)
    with patch("src.main.Prompt.ask", return_value="2"):
        result = select_single_file(None, candidates, "videos", "sin archivos")
    assert result == candidates[1]


def test_select_files_or_all_returns_all_on_zero(tmp_path):
    candidates = _make_candidates(tmp_path)
    with patch("src.main.Prompt.ask", return_value="0"):
        result = select_files_or_all(None, candidates, "videos", "sin archivos")
    assert result == candidates


def test_select_files_or_all_rejects_missing_direct_file():
    with patch("src.main.resolve_input_file", return_value=Path("/no/existe.mp4")):
        result = select_files_or_all("existe.mp4", [], "videos", "sin archivos")
    assert result == []
