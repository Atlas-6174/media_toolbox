from typer.testing import CliRunner

from src.main import app

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
