"""Configuracion de rutas del proyecto.

Todo el acceso a almacenamiento pasa por este modulo. En local usa la
carpeta data del repositorio. Para migrar a AWS basta con definir la
variable de entorno DATA_DIR, por ejemplo:

    DATA_DIR=s3://mi-bucket/accidentes-envigado
"""

import os
import shutil

DATA_DIR = os.environ.get("DATA_DIR", "data")

RAW_CSV = f"{DATA_DIR}/raw/accidentalidad_envigado.csv"
BRONZE = f"{DATA_DIR}/bronze/accidentes"
SILVER = f"{DATA_DIR}/silver/accidentes"
GOLD_SINIESTROS = f"{DATA_DIR}/gold/siniestros"
GOLD_AGREGADOS = f"{DATA_DIR}/gold/agregados"
GOLD_MODELOS = f"{DATA_DIR}/gold/modelos"

ES_NUBE = DATA_DIR.startswith("s3://")


def preparar(ruta):
    """Deja una ruta lista para escribir desde cero.

    En local borra la carpeta si existe y la vuelve a crear. En S3 no
    hace falta: cada corrida escribe objetos nuevos bajo el prefijo.
    """
    if ES_NUBE:
        return
    if os.path.isdir(ruta):
        shutil.rmtree(ruta)
    os.makedirs(ruta, exist_ok=True)
