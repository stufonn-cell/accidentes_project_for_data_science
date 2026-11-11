"""Storage paths and storage access for the project.

All storage access goes through this module. Locally it uses the data
folder of the repository. On AWS the Glue jobs set the DATA_DIR
environment variable to the lake bucket, for example:

    DATA_DIR=s3://my-bucket

Any DATA_DIR with a scheme (s3://, file://) goes through the pyarrow
filesystem layer, so the same code reads and writes S3 without s3fs.
"""

import io
import os
import shutil

import pandas as pd
from pyarrow import fs as pafs

DATA_DIR = os.environ.get("DATA_DIR", "data").rstrip("/")

RAW_CSV = f"{DATA_DIR}/raw/accidentalidad_envigado.csv"
BRONZE = f"{DATA_DIR}/bronze/accidentes"
SILVER = f"{DATA_DIR}/silver/accidentes"
EXPANDED = f"{DATA_DIR}/expandido/accidentes"
GOLD_SINIESTROS = f"{DATA_DIR}/gold/siniestros"
GOLD_AGREGADOS = f"{DATA_DIR}/gold/agregados"
GOLD_MODELOS = f"{DATA_DIR}/gold/modelos"

IS_CLOUD = "://" in DATA_DIR


def _filesystem(path):
    """Return the pyarrow filesystem and the path inside it, or (None, path) locally.

    Only DATA_DIR is parsed as a URI: pyarrow rejects non ASCII characters
    in URIs, such as the ñ of the año=2010 partitions, so the rest of the
    path is appended as plain text.
    """
    if not IS_CLOUD:
        return None, path
    if not path.startswith(DATA_DIR):
        raise ValueError(f"{path} is outside DATA_DIR {DATA_DIR}")
    filesystem, root = pafs.FileSystem.from_uri(DATA_DIR)
    return filesystem, root.rstrip("/") + path[len(DATA_DIR):]


def prepare(path):
    """Get a folder ready for a fresh write by removing what it holds.

    Without this, a second run on S3 would add new parquet files next to
    the old ones and duplicate the data.
    """
    filesystem, inner = _filesystem(path)
    if filesystem is not None:
        filesystem.delete_dir_contents(inner, missing_dir_ok=True)
        # S3 has no real folders; other filesystems need the folder to exist
        if not isinstance(filesystem, pafs.S3FileSystem):
            filesystem.create_dir(inner, recursive=True)
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def read_csv(path, **kwargs):
    filesystem, inner = _filesystem(path)
    if filesystem is None:
        return pd.read_csv(path, **kwargs)
    with filesystem.open_input_stream(inner) as f:
        return pd.read_csv(io.BytesIO(f.read()), **kwargs)


def read_parquet(path):
    filesystem, inner = _filesystem(path)
    return pd.read_parquet(inner, filesystem=filesystem)


def write_parquet(df, path, partition_cols=None):
    filesystem, inner = _filesystem(path)
    if partition_cols is None:
        # A single file goes inside its table folder, which may not exist yet
        parent = inner.rsplit("/", 1)[0]
        if filesystem is None:
            os.makedirs(parent, exist_ok=True)
        elif not isinstance(filesystem, pafs.S3FileSystem):
            filesystem.create_dir(parent, recursive=True)
    # Athena reads timestamps in milliseconds; pandas would write nanoseconds
    df.to_parquet(inner, filesystem=filesystem, index=False, partition_cols=partition_cols,
                  coerce_timestamps="ms", allow_truncated_timestamps=True)


def write_bytes(path, data):
    filesystem, inner = _filesystem(path)
    if filesystem is None:
        with open(path, "wb") as f:
            f.write(data)
        return
    with filesystem.open_output_stream(inner) as f:
        f.write(data)


def write_text(path, text):
    write_bytes(path, text.encode("utf-8"))
