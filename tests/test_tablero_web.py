"""Tests of the web dashboard served by the API: GET /tablero and the static page.

They need no trained model: the dashboard does not depend on it.

    python -m pytest tests/test_tablero_web.py
"""

import base64
import gzip
import json

import pytest
from fastapi.testclient import TestClient

from api import main
from api.main import app
from src import config

DATA = {"meta": {"filas": 3, "generado": "2026-11-21"}, "dic": {"meses": ["2024-01"]},
        "cubo": [[0, 0, 0, 0, 3, 1]] * 400}


def use_storage(monkeypatch, data_dir):
    """Point src.config at a storage root, as the DATA_DIR variable would."""
    data_dir = str(data_dir).replace("\\", "/").rstrip("/")
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "GOLD_TABLERO", f"{data_dir}/gold/tablero")
    monkeypatch.setattr(config, "TABLERO_JSON", f"{data_dir}/gold/tablero/datos.json")
    monkeypatch.setattr(config, "IS_CLOUD", "://" in data_dir)


def write_data(folder, data=DATA):
    path = folder / "gold" / "tablero" / "datos.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def forget_data():
    main.reset_tablero()
    yield
    main.reset_tablero()


@pytest.fixture
def client(tmp_path, monkeypatch):
    write_data(tmp_path)
    use_storage(monkeypatch, tmp_path)
    return TestClient(app)


def test_tablero_serves_the_stored_document(client):
    answer = client.get("/tablero")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/json"
    assert answer.headers["cache-control"].startswith("public, max-age=")
    assert answer.json() == DATA


def test_tablero_needs_no_api_key(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secreto")
    assert client.get("/tablero").status_code == 200


def test_tablero_is_compressed(client):
    answer = client.get("/tablero", headers={"Accept-Encoding": "gzip"})
    assert answer.headers["content-encoding"] == "gzip"
    assert answer.json() == DATA


def test_without_data_the_tablero_answers_503(tmp_path, monkeypatch):
    use_storage(monkeypatch, tmp_path)
    answer = TestClient(app).get("/tablero")
    assert answer.status_code == 503
    assert answer.json() == {"detail": "Datos del tablero no disponibles"}


def test_a_new_run_is_picked_up_after_the_cache_expires(client, tmp_path, monkeypatch):
    assert client.get("/tablero").json()["meta"]["filas"] == 3
    write_data(tmp_path, {**DATA, "meta": {"filas": 7}})
    assert client.get("/tablero").json()["meta"]["filas"] == 3  # still cached
    monkeypatch.setattr(main, "TABLERO_TTL_SECONDS", 0)
    assert client.get("/tablero").json()["meta"]["filas"] == 7


def test_the_cached_copy_is_served_when_storage_fails(client, tmp_path, monkeypatch):
    assert client.get("/tablero").status_code == 200
    (tmp_path / "gold" / "tablero" / "datos.json").unlink()
    monkeypatch.setattr(main, "TABLERO_TTL_SECONDS", 0)
    answer = client.get("/tablero")
    assert answer.status_code == 200
    assert answer.json() == DATA


def test_the_dashboard_page_is_served_at_the_root(client):
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert 'src="js/cargar.js"' in page.text
    script = client.get("/js/cargar.js")
    assert script.status_code == 200
    assert "/tablero" in script.text


def test_api_routes_are_not_shadowed_by_the_page(client):
    assert client.get("/openapi.json").json()["info"]["version"] == "2.1.0"
    assert "/tablero" in client.get("/openapi.json").json()["paths"]
    # Without a model /health answers 503 in JSON, not the dashboard page
    health = client.get("/health")
    assert health.headers["content-type"] == "application/json"


def test_unknown_files_are_404(client):
    assert client.get("/no-existe.js").status_code == 404


def gateway_event(path, headers=None):
    """An API Gateway HTTP API (payload 2.0) GET event, as Lambda receives it."""
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
        "headers": {"host": "example.execute-api.aws", **(headers or {})},
        "requestContext": {
            "accountId": "123456789012", "apiId": "example", "stage": "$default",
            "domainName": "example.execute-api.aws", "requestId": "id", "routeKey": "$default",
            "time": "21/Nov/2026:15:00:00 +0000", "timeEpoch": 1795186800000,
            "http": {"method": "GET", "path": path, "protocol": "HTTP/1.1",
                     "sourceIp": "127.0.0.1", "userAgent": "pytest"},
        },
        "isBase64Encoded": False,
    }


def test_lambda_serves_the_dashboard_and_its_data(client):
    from api.lambda_handler import handler

    page = handler(gateway_event("/"), None)
    assert page["statusCode"] == 200
    assert "cargar.js" in page["body"]

    data = handler(gateway_event("/tablero", {"accept-encoding": "gzip"}), None)
    assert data["statusCode"] == 200
    # Compressed bodies go back to API Gateway in base64
    assert data["isBase64Encoded"] is True
    assert json.loads(gzip.decompress(base64.b64decode(data["body"]))) == DATA
