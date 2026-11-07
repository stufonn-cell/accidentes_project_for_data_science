"""Storage paths for the project.

All storage access goes through this module. Locally it uses the data
folder of the repository. To migrate to AWS, set the DATA_DIR
environment variable, for example:

    DATA_DIR=s3://my-bucket/accidentes-envigado
"""

import os
import shutil

DATA_DIR = os.environ.get("DATA_DIR", "data")

RAW_CSV = f"{DATA_DIR}/raw/accidentalidad_envigado.csv"
BRONZE = f"{DATA_DIR}/bronze/accidentes"
SILVER = f"{DATA_DIR}/silver/accidentes"
EXPANDED = f"{DATA_DIR}/expandido/accidentes"
GOLD_SINIESTROS = f"{DATA_DIR}/gold/siniestros"
GOLD_AGREGADOS = f"{DATA_DIR}/gold/agregados"
GOLD_MODELOS = f"{DATA_DIR}/gold/modelos"

IS_CLOUD = DATA_DIR.startswith("s3://")


def prepare(path):
    """Get a path ready for a fresh write.

    Locally it removes the folder and creates it again. On S3 this is
    not needed: each run writes new objects under the prefix.
    """
    if IS_CLOUD:
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
