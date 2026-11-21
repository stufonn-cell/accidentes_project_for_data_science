"""Functional tests of the prediction API with FastAPI's TestClient.

The tests use the model trained by the pipeline on the RUNT data. Copy it
once before running them (build/ is not versioned):

    mkdir -p build/api_fixture/gold
    cp -r data/gold/modelos build/api_fixture/gold/modelos

Each test copies that model to its own storage folder, so the tests never
read or write the data folder of the repository.

Run them with:  python -m pytest tests/test_api_prediccion.py -v
"""

import hashlib
import json
import pathlib
import shutil

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import Pipeline

from api import model_store, register_model
from api.main import app
from api.schemas import MAX_BATCH
from src import config

ROOT = pathlib.Path(__file__).resolve().parents[1]
REAL_FIXTURE = ROOT / "build" / "api_fixture" / "gold" / "modelos"

pytestmark = pytest.mark.skipif(
    not (REAL_FIXTURE / "metricas.json").exists(),
    reason="build/api_fixture is not there: copy data/gold/modelos into it")

VEHICLE = {
    "tipo": "MOTOCICLETA",
    "marca": "AKT",
    "modelo": 2023,
    "fecha": "06/2024",
    "departamento": "ANTIOQUIA",
    "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE",
}


def description():
    return json.loads((REAL_FIXTURE / "metricas.json").read_text(encoding="utf-8"))


def use_storage(monkeypatch, data_dir):
    """Point src.config at a storage root, as the DATA_DIR variable would."""
    data_dir = str(data_dir).replace("\\", "/").rstrip("/")
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "GOLD_MODELOS", f"{data_dir}/gold/modelos")
    monkeypatch.setattr(config, "IS_CLOUD", "://" in data_dir)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("MODEL_VERSION", raising=False)
    model_store.reset_service()


def copy_real_model(folder, **changes):
    """The trained model and its metricas.json, with optional changes to the JSON."""
    models = folder / "gold" / "modelos"
    models.mkdir(parents=True, exist_ok=True)
    data = description()
    shutil.copy(REAL_FIXTURE / f"{data['mejor_modelo']}.joblib", models)
    data.update(changes)
    (models / "metricas.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return models


def write_dummy_model(folder, version):
    """A different model under the same name, as a new training would leave it."""
    data = description()
    features = data["variables"]["categoricas"] + data["variables"]["numericas"]
    frame = pd.DataFrame([{name: 0 for name in features}] * 4)
    model = Pipeline([("clasificador", DummyClassifier(strategy="prior"))])
    model.fit(frame, [0, 0, 0, 1])
    models = folder / "gold" / "modelos"
    joblib.dump(model, models / f"{data['mejor_modelo']}.joblib")
    data["version"] = version
    (models / "metricas.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture(autouse=True)
def forget_model():
    yield
    model_store.reset_service()


@pytest.fixture
def client(tmp_path, monkeypatch):
    copy_real_model(tmp_path)
    use_storage(monkeypatch, tmp_path)
    return TestClient(app)


# ---------------------------------------------------------------- health

def test_health_describes_the_loaded_model(client, tmp_path):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    data = description()
    assert body["estado"] == "ok"
    assert body["modelo"] == data["mejor_modelo"]
    assert body["version"] == data["version"]
    assert body["objetivo"] == "con_muertos"
    assert body["umbral_decision"] == data["umbral_decision"]
    assert body["variables"] == data["variables"]
    raw = (tmp_path / "gold" / "modelos" / f"{data['mejor_modelo']}.joblib").read_bytes()
    assert body["sha256"] == hashlib.sha256(raw).hexdigest()
    assert body["requiere_api_key"] is False


def test_version_falls_back_to_the_hash_of_the_model(tmp_path, monkeypatch):
    copy_real_model(tmp_path, version=None)
    use_storage(monkeypatch, tmp_path)
    body = TestClient(app).get("/health").json()
    assert body["version"] == "sha256-" + body["sha256"][:12]


def test_openapi_docs_are_published(client):
    schema = client.get("/openapi.json").json()
    assert {"/health", "/predict", "/predict/batch"} <= set(schema["paths"])
    assert client.get("/docs").status_code == 200


# --------------------------------------------------------------- predict

def test_valid_prediction(client):
    response = client.post("/predict", json=VEHICLE)
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["probabilidad"] <= 1.0
    assert body["alerta"] == (body["probabilidad"] >= body["umbral_decision"])
    assert body["version"] == description()["version"]
    assert body["categorias_agrupadas"] == [] and body["categorias_desconocidas"] == []
    # Derived as src/silver.py does: edad = anio - modelo, mes from the date
    assert body["entrada_modelo"] == {
        "tipo_grupo": "MOTOCICLETA", "marca_grupo": "AKT", "departamento": "ANTIOQUIA",
        "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE", "modelo": 2023.0, "edad": 1.0,
        "mes": 6.0}


def test_the_cases_of_the_training_report_are_reproduced(client):
    """The API, fed with natural fields, gives the probabilities of metricas.json."""
    cases = description()["casos"]
    assert cases
    for case in cases:
        vehicle = {
            "tipo": case["tipo_grupo"].lower(), "marca": case["marca_grupo"].title(),
            "modelo": case["modelo"], "anio": case["modelo"] + case["edad"], "mes": case["mes"],
            "departamento": case["departamento"], "autoridad": case["autoridad"].lower(),
        }
        body = client.post("/predict", json=vehicle).json()
        assert body["probabilidad"] == pytest.approx(case["probabilidad"], abs=1e-4), case["caso"]
        assert body["alerta"] == bool(case["alerta"]), case["caso"]


def test_prediction_matches_the_model_called_directly(client, tmp_path):
    data = description()
    model = joblib.load(tmp_path / "gold" / "modelos" / f"{data['mejor_modelo']}.joblib")
    row = pd.DataFrame([{"tipo_grupo": "MOTOCICLETA", "marca_grupo": "AKT",
                         "departamento": "ANTIOQUIA",
                         "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE",
                         "modelo": 2023.0, "edad": 1.0, "mes": 6.0}])
    expected = model.predict_proba(row)[0, 1]
    assert client.post("/predict", json=VEHICLE).json()["probabilidad"] == pytest.approx(
        expected, abs=1e-4)


def test_fecha_and_anio_mes_give_the_same_answer(client):
    by_date = client.post("/predict", json=VEHICLE).json()
    by_parts = client.post("/predict", json=dict(
        {k: v for k, v in VEHICLE.items() if k != "fecha"}, anio=2024, mes=6)).json()
    assert by_date == by_parts


def test_age_is_floored_at_zero(client):
    body = client.post("/predict", json=dict(VEHICLE, modelo=2025, fecha="06/2024")).json()
    assert body["entrada_modelo"]["edad"] == 0.0


def test_missing_model_year_is_sent_as_unknown(client):
    body = client.post("/predict", json={k: v for k, v in VEHICLE.items() if k != "modelo"})
    assert body.status_code == 200
    assert body.json()["entrada_modelo"]["modelo"] is None
    assert body.json()["entrada_modelo"]["edad"] is None


@pytest.mark.parametrize("threshold, expected", [(0.01, True), (0.99, False)])
def test_decision_follows_the_threshold(tmp_path, monkeypatch, threshold, expected):
    copy_real_model(tmp_path, umbral_decision=threshold)
    use_storage(monkeypatch, tmp_path)
    body = TestClient(app).post("/predict", json=VEHICLE).json()
    assert body["umbral_decision"] == threshold
    assert 0.01 < body["probabilidad"] < 0.99
    assert body["alerta"] is expected


def test_texts_are_cleaned_like_the_silver_layer(client):
    exact = client.post("/predict", json=dict(VEHICLE, departamento="BOGOTA D.C.",
                                              autoridad="SECRETARIA DISTRITAL DE MOVILIDAD DE BOGOTA")).json()
    loose = client.post("/predict", json=dict(VEHICLE, departamento="  Bogotá  d.c. ",
                                              autoridad="Secretaría distrital de movilidad de Bogotá",
                                              tipo="motocicleta", marca="akt")).json()
    assert loose["categorias_desconocidas"] == [] and loose["categorias_agrupadas"] == []
    assert loose["probabilidad"] == exact["probabilidad"]


def test_rare_type_and_brand_go_to_the_other_group(client):
    body = client.post("/predict", json=dict(VEHICLE, tipo="PATINETA ELECTRICA",
                                             marca="MARCA INVENTADA")).json()
    assert body["categorias_agrupadas"] == ["tipo_grupo", "marca_grupo"]
    assert body["entrada_modelo"]["tipo_grupo"] == "OTRO"
    assert body["entrada_modelo"]["marca_grupo"] == "OTRAS"


def test_missing_brand_goes_to_the_other_group(client):
    body = client.post("/predict", json={k: v for k, v in VEHICLE.items() if k != "marca"}).json()
    assert body["entrada_modelo"]["marca_grupo"] == "OTRAS"


def test_unknown_authority_does_not_fail(client):
    response = client.post("/predict", json=dict(VEHICLE, autoridad="TRANSITO QUE NO EXISTE"))
    assert response.status_code == 200
    body = response.json()
    assert body["categorias_desconocidas"] == ["autoridad"]
    assert 0.0 <= body["probabilidad"] <= 1.0


# ------------------------------------------------------------ validation

@pytest.mark.parametrize("change, field", [
    ({"tipo": None}, "tipo"),
    ({"departamento": None}, "departamento"),
    ({"autoridad": ""}, "autoridad"),
    ({"marca": "x" * 121}, "marca"),
    ({"marca": "linea\ncon salto"}, "marca"),
    ({"tipo": 7}, "tipo"),
    ({"modelo": 1900}, "modelo"),
    ({"modelo": "dos mil"}, "modelo"),
    ({"fecha": "2024-06"}, "vehiculo"),
    ({"fecha": "13/2024"}, "vehiculo"),
    ({"fecha": "06/1850"}, "vehiculo"),
    ({"fecha": None}, "vehiculo"),
    ({"fecha": None, "anio": 2024}, "vehiculo"),
    ({"fecha": None, "anio": 2024, "mes": 13}, "mes"),
    ({"anio": 2023, "mes": 6}, "vehiculo"),
    ({"modelo": 2026, "fecha": "06/2024"}, "vehiculo"),
    ({"campo_inventado": "x"}, "campo_inventado"),
    ({"identificador": "../../etc/passwd"}, "identificador"),
])
def test_invalid_input_is_rejected_with_422(client, change, field):
    body = {k: v for k, v in dict(VEHICLE, **change).items() if v is not None}
    response = client.post("/predict", json=body)
    assert response.status_code == 422
    problems = response.json()["detail"]
    assert any(problem["campo"].startswith(field) for problem in problems)
    assert all(set(problem) == {"campo", "mensaje"} for problem in problems)


def test_body_that_is_not_json_is_rejected(client):
    response = client.post("/predict", content=b"{no es json",
                           headers={"content-type": "application/json"})
    assert response.status_code == 422


def test_oversized_body_is_rejected(client):
    response = client.post("/predict", content=b"x" * (300 * 1024),
                           headers={"content-type": "application/json"})
    assert response.status_code == 413


# ----------------------------------------------------------------- batch

def test_batch_gives_the_same_as_one_by_one(client):
    vehicles = [
        dict(VEHICLE, identificador="V-1"),
        dict(VEHICLE, identificador="V-2", tipo="TRACTOCAMION", marca="KENWORTH",
             modelo=2012, fecha="12/2024", departamento="CESAR"),
        dict(VEHICLE, identificador="V-3", autoridad="OTRO PLANETA"),
    ]
    response = client.post("/predict/batch", json={"vehiculos": vehicles})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [p["identificador"] for p in body["predicciones"]] == ["V-1", "V-2", "V-3"]
    assert body["predicciones"][2]["categorias_desconocidas"] == ["autoridad"]
    for vehicle, prediction in zip(vehicles, body["predicciones"]):
        single = client.post("/predict", json=vehicle).json()
        assert prediction["probabilidad"] == single["probabilidad"]
        assert prediction["alerta"] == single["alerta"]


@pytest.mark.parametrize("size", [0, MAX_BATCH + 1])
def test_batch_size_is_bounded(client, size):
    response = client.post("/predict/batch", json={"vehiculos": [VEHICLE] * size})
    assert response.status_code == 422


def test_batch_error_says_which_vehicle(client):
    bad = {k: v for k, v in VEHICLE.items() if k != "autoridad"}
    response = client.post("/predict/batch", json={"vehiculos": [VEHICLE, bad]})
    assert response.status_code == 422
    assert response.json()["detail"][0]["campo"] == "vehiculos.1.autoridad"


# ---------------------------------------------------------------- errors

def test_without_model_the_service_answers_503(tmp_path, monkeypatch):
    use_storage(monkeypatch, tmp_path)  # empty folder: there is no model
    with TestClient(app) as client:
        for response in (client.get("/health"), client.post("/predict", json=VEHICLE)):
            assert response.status_code == 503
            assert response.json() == {"detail": "Modelo no disponible"}


def test_unsafe_model_name_is_not_loaded(tmp_path, monkeypatch):
    """The model name of metricas.json cannot point outside the model folder."""
    copy_real_model(tmp_path, mejor_modelo="../../otro")
    use_storage(monkeypatch, tmp_path)
    assert TestClient(app).get("/health").status_code == 503


@pytest.mark.parametrize("variables", [
    None,
    {"categoricas": ["barrio"], "numericas": ["mes"]},
])
def test_model_with_variables_the_api_cannot_build_is_not_served(tmp_path, monkeypatch,
                                                                 variables):
    copy_real_model(tmp_path, variables=variables)
    use_storage(monkeypatch, tmp_path)
    assert TestClient(app).get("/health").status_code == 503


def test_unexpected_error_does_not_leak_details(client, monkeypatch):
    def broken(self, rows):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(model_store.ModelService, "predict", broken)
    failing = TestClient(app, raise_server_exceptions=False)
    response = failing.post("/predict", json=VEHICLE)
    assert response.status_code == 500
    assert response.json() == {"detail": "Error interno"}
    assert "secret" not in response.text and "Traceback" not in response.text


# --------------------------------------------------------------- api key

def test_api_key_protects_predictions(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "clave-de-prueba")
    assert client.get("/health").json()["requiere_api_key"] is True
    assert client.post("/predict", json=VEHICLE).status_code == 401
    assert client.post("/predict", json=VEHICLE,
                       headers={"X-API-Key": "otra"}).status_code == 401
    assert client.post("/predict/batch", json={"vehiculos": [VEHICLE]}).status_code == 401
    assert client.post("/predict", json=VEHICLE,
                       headers={"X-API-Key": "clave-de-prueba"}).status_code == 200


# ------------------------------------------------------------ versioning

def test_registered_version_survives_a_new_training(client, tmp_path, monkeypatch, capsys):
    version = description()["version"]
    before = client.post("/predict", json=VEHICLE).json()

    register_model.main()
    folder = tmp_path / "registro_modelos" / version
    manifest = json.loads((folder / "manifiesto.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version
    assert manifest["sha256"] == client.get("/health").json()["sha256"]
    register_model.main()  # registering the same model twice changes nothing
    assert "already registered" in capsys.readouterr().out

    # A new training replaces gold/modelos with another model and version
    write_dummy_model(tmp_path, "runt-nueva-prueba")
    model_store.reset_service()
    assert client.get("/health").json()["version"] == "runt-nueva-prueba"
    assert client.post("/predict", json=VEHICLE).json()["probabilidad"] != before["probabilidad"]

    # The older version is still there and can be served again
    monkeypatch.setenv("MODEL_VERSION", version)
    model_store.reset_service()
    health = client.get("/health").json()
    assert health["version"] == version
    assert health["origen"].endswith(f"registro_modelos/{version}/modelo.joblib")
    assert client.post("/predict", json=VEHICLE).json() == before


def test_a_version_cannot_be_overwritten(client, tmp_path):
    register_model.main()
    # Same version name, different model file
    write_dummy_model(tmp_path, description()["version"])
    model_store.reset_service()
    with pytest.raises(SystemExit, match="immutable"):
        register_model.main()


def test_version_name_cannot_leave_the_registry(client, monkeypatch):
    monkeypatch.setenv("MODEL_VERSION", "../gold/modelos")
    model_store.reset_service()
    assert client.get("/health").status_code == 503


# ------------------------------------------------- storage through a URI

def test_model_loads_through_the_uri_filesystem(tmp_path, monkeypatch):
    """Same code path as DATA_DIR=s3://bucket, with a file:// URI instead."""
    copy_real_model(tmp_path)
    use_storage(monkeypatch, tmp_path.as_uri())
    assert config.IS_CLOUD
    client = TestClient(app)
    assert client.get("/health").json()["origen"].startswith("file://")
    assert client.post("/predict", json=VEHICLE).status_code == 200


# ------------------------------------------------------------ aws lambda

def gateway_event(method, path, body=None):
    """An API Gateway HTTP API (payload 2.0) event, as Lambda receives it."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json", "host": "example.execute-api.aws"},
        "requestContext": {
            "accountId": "123456789012", "apiId": "example", "stage": "$default",
            "domainName": "example.execute-api.aws", "requestId": "id", "routeKey": "$default",
            "time": "20/Nov/2026:15:00:00 +0000", "timeEpoch": 1795100400000,
            "http": {"method": method, "path": path, "protocol": "HTTP/1.1",
                     "sourceIp": "127.0.0.1", "userAgent": "pytest"},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


def test_lambda_handler_answers_api_gateway_events(client):
    from api.lambda_handler import handler

    health = handler(gateway_event("GET", "/health"), None)
    assert health["statusCode"] == 200
    assert json.loads(health["body"])["modelo"] == description()["mejor_modelo"]

    prediction = handler(gateway_event("POST", "/predict", VEHICLE), None)
    assert prediction["statusCode"] == 200
    assert prediction["headers"]["content-type"] == "application/json"
    assert json.loads(prediction["body"]) == client.post("/predict", json=VEHICLE).json()

    invalid = handler(gateway_event("POST", "/predict", {"tipo": "MOTO"}), None)
    assert invalid["statusCode"] == 422
