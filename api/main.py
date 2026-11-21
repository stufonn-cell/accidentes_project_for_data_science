"""FastAPI application: health check and predictions of the published model.

Run it locally with:

    python -m uvicorn api.main:app --host 127.0.0.1 --port 8020

DATA_DIR chooses the storage (local folder or s3://bucket), MODEL_VERSION
pins a registered version and API_KEY, when set, protects the predictions.
"""

import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from api import model_store
from api.schemas import (Lote, Prediccion, RespuestaLote, RespuestaPrediccion, Salud,
                         Vehiculo)

logger = logging.getLogger("api")

# A batch of 100 vehicles is under 40 KB; anything bigger is not a real request
MAX_BODY_BYTES = 256 * 1024

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@asynccontextmanager
async def lifespan(app):
    # Load at start-up so the first request is fast. A failure is logged and
    # the service stays up answering 503 until the model can be read.
    try:
        model_store.get_service()
    except model_store.ModelNotAvailable as error:
        logger.error("model not loaded at start-up: %s", error)
    yield


app = FastAPI(
    title="API de prediccion de siniestros con muertos - RUNT Colombia",
    description="Recibe un vehiculo involucrado en un siniestro con victimas (RUNT, Ley 2251 "
                "de 2022) y devuelve la probabilidad de que el siniestro tenga muertos, con "
                "una alerta segun el umbral de decision del modelo publicado.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
        return JSONResponse(status_code=413, content={"detail": "Cuerpo demasiado grande"})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    # Field and reason only: the default answer also echoes the input back
    # Rules over several fields (date, model year) have no field: "vehiculo"
    problems = [{
        "campo": ".".join(str(part) for part in item.get("loc", ()) if part != "body") or "vehiculo",
        "mensaje": item.get("msg", ""),
    } for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": problems})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    logger.exception("unexpected error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno"})


def service():
    try:
        return model_store.get_service()
    except model_store.ModelNotAvailable as error:
        logger.error("model not available: %s", error)
        raise HTTPException(status_code=503, detail="Modelo no disponible") from None


def check_api_key(key: str = Depends(api_key_header)):
    expected = os.environ.get("API_KEY", "")
    if not expected:
        return
    if not key or not hmac.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(status_code=401,
                            detail="Falta el encabezado X-API-Key o no es valido")


def to_predictions(model, vehicles):
    built = [model.build_row(vehicle) for vehicle in vehicles]
    probabilities = [round(p, 4) for p in model.predict([row for row, _, _ in built])]
    # The decision uses the rounded value, so each answer is consistent with itself
    return [Prediccion(
        identificador=vehicle.identificador,
        probabilidad=probability,
        alerta=probability >= model.threshold,
        entrada_modelo={k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()},
        categorias_agrupadas=grouped,
        categorias_desconocidas=unknown,
    ) for vehicle, probability, (row, grouped, unknown) in zip(vehicles, probabilities, built)]


@app.get("/health", response_model=Salud, summary="Estado del servicio y modelo cargado")
def health(model=Depends(service)):
    return Salud(
        estado="ok",
        modelo=model.name,
        version=model.version,
        sha256=model.sha256,
        objetivo=model.target,
        umbral_decision=model.threshold,
        variables={"categoricas": model.categorical, "numericas": model.numeric},
        origen=model.source,
        requiere_api_key=bool(os.environ.get("API_KEY")),
    )


@app.post("/predict", response_model=RespuestaPrediccion,
          summary="Probabilidad de muertos para un vehiculo",
          dependencies=[Depends(check_api_key)])
def predict(vehicle: Vehiculo, model=Depends(service)):
    prediction = to_predictions(model, [vehicle])[0]
    return RespuestaPrediccion(**prediction.model_dump(), umbral_decision=model.threshold,
                               modelo=model.name, version=model.version)


@app.post("/predict/batch", response_model=RespuestaLote,
          summary="Probabilidad de muertos para hasta 100 vehiculos",
          dependencies=[Depends(check_api_key)])
def predict_batch(batch: Lote, model=Depends(service)):
    predictions = to_predictions(model, batch.vehiculos)
    return RespuestaLote(modelo=model.name, version=model.version,
                         umbral_decision=model.threshold, total=len(predictions),
                         predicciones=predictions)
