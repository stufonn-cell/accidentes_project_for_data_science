"""Loads the trained model from the project storage and builds its inputs.

The model and its description (metricas.json) are read through src.config,
so the same code works with the local data folder and with the S3 bucket
(DATA_DIR=s3://bucket). Only files of the project's own storage are ever
unpickled: the path is built here, never taken from a request.
"""

import hashlib
import io
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field

import joblib
import pandas as pd

from src import config
from src.silver import OTHER_BRAND, OTHER_TYPE, normalize_text

logger = logging.getLogger("api")

DEFAULT_THRESHOLD = 0.5

# Variables the API can build from a request. The grouped ones fall back
# to the "other" group of src/silver.py when the model did not see them.
CATEGORICAL_SOURCES = {"tipo_grupo": "tipo", "marca_grupo": "marca",
                       "departamento": "departamento", "autoridad": "autoridad"}
GROUPED = {"tipo_grupo": OTHER_TYPE, "marca_grupo": OTHER_BRAND}
NUMERIC_SUPPORTED = ("modelo", "edad", "mes")

# Names allowed for a model or a version: they end up inside a storage path
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ModelNotAvailable(Exception):
    """The model could not be loaded. The message is for the log, not for the caller."""


def registry_dir():
    """Folder with the immutable copies of each published model version.

    It lives outside gold/modelos because the training stage empties that
    folder on every run.
    """
    return f"{config.DATA_DIR}/registro_modelos"


def normalize(value):
    """Text cleaned exactly as src/silver.py cleans the source columns."""
    return normalize_text(pd.Series([value], dtype=object)).iloc[0]


def derive(vehicle):
    """Model variables of one validated request (api.schemas.Vehiculo).

    edad follows src/silver.py: age at the accident, anio - modelo,
    floored at 0. A missing model year leaves modelo and edad empty, as
    silver does with an impossible one.
    """
    texts = {name: normalize(getattr(vehicle, source))
             for name, source in CATEGORICAL_SOURCES.items()}
    modelo = vehicle.modelo
    numbers = {
        "modelo": float(modelo) if modelo is not None else math.nan,
        "edad": float(max(vehicle.anio - modelo, 0)) if modelo is not None else math.nan,
        "mes": float(vehicle.mes),
    }
    return texts, numbers


def known_categories(model):
    """Categories each encoder saw in training, as {column: set of values}.

    Best effort: it walks the usual scikit-learn containers. A model with
    another shape simply gets no table, and values are passed as they come.
    """
    found = {}
    pending, seen = [model], set()
    while pending and len(seen) < 200:
        item = pending.pop()
        if item is None or isinstance(item, str) or id(item) in seen:
            continue
        seen.add(id(item))
        for _, transformer, columns in getattr(item, "transformers_", []):
            encoder = transformer
            if hasattr(transformer, "steps"):
                encoders = [s for _, s in transformer.steps if hasattr(s, "categories_")]
                encoder = encoders[0] if encoders else None
            categories = getattr(encoder, "categories_", None)
            if categories is None or not isinstance(columns, (list, tuple)):
                continue
            if len(categories) != len(columns):
                continue
            for column, values in zip(columns, categories):
                found[str(column)] = {v for v in values if isinstance(v, str)}
        pending.extend(step for _, step in getattr(item, "steps", []))
        for attribute in ("estimator", "estimator_", "base_estimator"):
            pending.append(getattr(item, attribute, None))
        for calibrated in getattr(item, "calibrated_classifiers_", [])[:1]:
            pending.append(getattr(calibrated, "estimator", None))
    return found


@dataclass
class ModelService:
    model: object
    name: str
    version: str
    sha256: str
    source: str
    categorical: list
    numeric: list
    threshold: float
    target: str
    categories: dict = field(default_factory=dict)

    @property
    def features(self):
        return self.categorical + self.numeric

    def build_row(self, vehicle):
        """One model input row from a request.

        Returns the row, the grouped variables whose value went to the
        "other" group (rare or new type or brand, like src/silver.py does)
        and the variables whose value the model never saw. Unknown values
        do not fail: the encoders treat them as an unknown category.
        """
        texts, numbers = derive(vehicle)
        row, grouped, unknown = {}, [], []
        for name in self.categorical:
            value = texts[name]
            known = self.categories.get(name)
            if known is not None and value not in known:
                if name in GROUPED:
                    value = GROUPED[name]
                    grouped.append(name)
                else:
                    unknown.append(name)
            row[name] = value
        for name in self.numeric:
            row[name] = numbers[name]
        return row, grouped, unknown

    def predict(self, rows):
        """Probability of the target for each row built with build_row."""
        frame = pd.DataFrame(rows, columns=self.features)
        for name in self.categorical:
            frame[name] = frame[name].astype(object)
        for name in self.numeric:
            frame[name] = frame[name].astype("float64")
        order = getattr(self.model, "feature_names_in_", None)
        if order is not None and set(order) == set(frame.columns):
            frame = frame[list(order)]
        probabilities = self.model.predict_proba(frame)[:, 1]
        return [min(1.0, max(0.0, float(p))) for p in probabilities]


def _read_json(path):
    return json.loads(config.read_bytes(path).decode("utf-8"))


def load_service():
    """Read metricas.json and the model it points to.

    With MODEL_VERSION set, the model comes from the registry folder of
    that version instead of the latest training output.
    """
    pinned = os.environ.get("MODEL_VERSION", "").strip()
    try:
        if pinned:
            if not SAFE_NAME.match(pinned):
                raise ModelNotAvailable("MODEL_VERSION has characters that are not allowed")
            folder = f"{registry_dir()}/{pinned}"
            description = _read_json(f"{folder}/metricas.json")
            model_path = f"{folder}/modelo.joblib"
        else:
            folder = config.GOLD_MODELOS
            description = _read_json(f"{folder}/metricas.json")
            model_path = None

        name = str(description.get("mejor_modelo", ""))
        if not SAFE_NAME.match(name):
            raise ModelNotAvailable("metricas.json has no valid mejor_modelo")
        if model_path is None:
            model_path = f"{folder}/{name}.joblib"
        raw = config.read_bytes(model_path)
    except ModelNotAvailable:
        raise
    except Exception as error:
        raise ModelNotAvailable(f"cannot read the model from {config.DATA_DIR}: {error}") from error

    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        model = joblib.load(io.BytesIO(raw))
    except Exception as error:
        raise ModelNotAvailable(f"cannot load {model_path}: {error}") from error
    if not hasattr(model, "predict_proba"):
        raise ModelNotAvailable(f"{model_path} is not a classifier with predict_proba")

    variables = description.get("variables") or {}
    categorical = [str(v) for v in variables.get("categoricas") or []]
    numeric = [str(v) for v in variables.get("numericas") or []]
    unsupported = ([v for v in categorical if v not in CATEGORICAL_SOURCES]
                   + [v for v in numeric if v not in NUMERIC_SUPPORTED])
    if not categorical and not numeric:
        raise ModelNotAvailable("metricas.json does not describe the model variables")
    if unsupported:
        raise ModelNotAvailable(f"the API cannot build these model variables: {unsupported}")

    try:
        threshold = float(description.get("umbral_decision", DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        threshold = DEFAULT_THRESHOLD
    if not 0.0 < threshold < 1.0:
        threshold = DEFAULT_THRESHOLD

    # Without a version from training, the content of the file identifies it
    version = str(description.get("version") or "").strip() or f"sha256-{sha256[:12]}"
    if not SAFE_NAME.match(version):
        raise ModelNotAvailable("metricas.json has a version with characters that are not allowed")
    if pinned and version != pinned:
        raise ModelNotAvailable(f"the registry folder {pinned} holds version {version}")

    service = ModelService(
        model=model, name=name, version=version, sha256=sha256, source=model_path,
        categorical=categorical, numeric=numeric, threshold=threshold,
        target=str(description.get("objetivo", "con_muertos")),
        categories=known_categories(model),
    )
    logger.info("model %s version %s loaded from %s", name, version, model_path)
    return service


_service = None


def get_service():
    """The loaded model, read once per process and kept in memory."""
    global _service
    if _service is None:
        _service = load_service()
    return _service


def reset_service():
    """Forget the loaded model, so the next request reads it again."""
    global _service
    _service = None
