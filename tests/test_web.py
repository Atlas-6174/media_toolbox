from fastapi.testclient import TestClient

from src.web.app import app

client = TestClient(app)


def test_web_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "MediaBox" in response.text
    assert "Extraer Audio" in response.text


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
