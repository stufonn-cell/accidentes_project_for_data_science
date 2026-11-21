"""Publishes the current model as an immutable version in the model registry.

Copies the best model of gold/modelos and its metricas.json to

    <DATA_DIR>/registro_modelos/<version>/modelo.joblib
    <DATA_DIR>/registro_modelos/<version>/metricas.json
    <DATA_DIR>/registro_modelos/<version>/manifiesto.json

The training stage empties gold/modelos on every run, so without this copy
an older model could not be served again. A version is never overwritten
with a different file. The API serves a registered version when the
MODEL_VERSION environment variable names it.

Usage:
    python -m api.register_model
    DATA_DIR=s3://my-bucket python -m api.register_model
"""

import hashlib
import json
import os
import platform
from datetime import datetime, timezone

import sklearn

from api import model_store
from src import config


def main():
    if os.environ.get("MODEL_VERSION"):
        raise SystemExit("Unset MODEL_VERSION: this command registers the latest trained model")
    service = model_store.load_service()

    folder = f"{model_store.registry_dir()}/{service.version}"
    raw = config.read_bytes(service.source)

    try:
        existing = config.read_bytes(f"{folder}/modelo.joblib")
    except Exception:
        existing = None
    if existing is not None:
        if hashlib.sha256(existing).hexdigest() == service.sha256:
            print(f"Version {service.version} was already registered in {folder}")
            return
        raise SystemExit(f"Version {service.version} already exists with a different model. "
                         "Versions are immutable: train again so it gets a new version.")

    if not config.IS_CLOUD:
        os.makedirs(folder, exist_ok=True)
    manifest = {
        "version": service.version,
        "modelo": service.name,
        "sha256": service.sha256,
        "bytes": len(raw),
        "origen": service.source,
        "registrado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "umbral_decision": service.threshold,
        "variables": {"categoricas": service.categorical, "numericas": service.numeric},
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
    }
    config.write_bytes(f"{folder}/modelo.joblib", raw)
    config.write_bytes(f"{folder}/metricas.json",
                       config.read_bytes(f"{config.GOLD_MODELOS}/metricas.json"))
    config.write_text(f"{folder}/manifiesto.json",
                      json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Registered {service.name} as version {service.version} in {folder}")
    print(f"Serve it with MODEL_VERSION={service.version}")


if __name__ == "__main__":
    main()
