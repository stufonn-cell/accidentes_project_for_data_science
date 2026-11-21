"""AWS Lambda entry point: the same FastAPI app behind API Gateway (HTTP API).

Mangum translates the API Gateway event into the ASGI call that FastAPI
understands, so there is no second implementation of the API for AWS.
"""

import logging

from mangum import Mangum

from api import model_store
from api.main import app

logging.getLogger().setLevel(logging.INFO)

# Load the model while the container starts, not on the first request.
# A failure here is not fatal: the API answers 503 and tries again later.
try:
    model_store.get_service()
except model_store.ModelNotAvailable as error:
    logging.getLogger("api").error("model not loaded at start-up: %s", error)

# lifespan="off": Mangum would run the start-up code on every invocation
handler = Mangum(app, lifespan="off")
