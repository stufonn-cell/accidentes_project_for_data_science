"""Ingestion: brings the source dataset into the raw zone of the lake.

First step of the pipeline. Downloads "Vehiculos involucrados en un
accidente de transito, Ley 2251 de 2022" (Ministerio de Transporte, RUNT)
from the open data portal datos.gov.co (Socrata API, dataset 6jmc-vaxk),
validates it and publishes it where the bronze stage reads:

    raw/vehiculos_siniestros_runt.csv                       current copy
    raw/manifiesto.json                                     what it is and how it was checked
    raw/historico/fecha_ingesta=YYYY-MM-DD/                 one snapshot per change of the source
    raw/rechazados/fecha_ingesta=YYYY-MM-DD/                downloads that failed validation

The checks follow the base document: the 9 columns, dates in MM/AAAA,
severity with only its two values, and a reasonable number of rows and
empty values. A download that fails validation never replaces the
current copy: the run ends with an error and the list of failed checks.
If the portal does not answer, the run goes on with the backup copy
(raw/respaldo/ or the current copy) and records it in the manifest.

Runs the same way on a laptop and as a Glue Python shell job:

    python -m src.ingesta                          # downloads, writes under data/
    python -m src.ingesta --archivo path.csv       # ingests a local copy of the CSV
    python -m src.ingesta --data-dir s3://bucket   # writes to the lake bucket

The pipeline (src.pipeline) does not download: it re-validates the
current raw copy with check_current() and stops if it fails.

Only the standard library is used, plus boto3 when the target is S3, so
the job needs no extra packages. Written for Python 3.9, the version of
Glue Python shell.
"""

import argparse
import csv
import datetime
import hashlib
import http.client
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PORTAL = "https://www.datos.gov.co"
DATASET_ID = "6jmc-vaxk"
RESOURCE_URL = f"{PORTAL}/resource/{DATASET_ID}"
FILE_NAME = "vehiculos_siniestros_runt.csv"

# Field name in the API -> column name in the raw CSV. The API lowers the
# names; the raw zone keeps the names of the CSV published by the RUNT.
COLUMNS = ["MARCA_VEHICULO", "MODELO_VEHICULO", "TIPO_VEHICULO", "EDAD_VEHICULO", "FECHA_ACCIDENTE",
           "GRAVEDAD_ACCIDENTE", "DEPARTAMENTO_ACCIDENTE", "MUNICIPIO_ACCIDENTE", "AUTORIDAD_DE_TRANSITO"]
FIELDS = {c.lower(): c for c in COLUMNS}

SEVERITIES = {"CON HERIDOS", "CON MUERTOS"}
MIN_ROWS = 100_000
FIRST_YEAR = 2022  # the law that created the register is from 2022
# Share of rows that may fail a row level check (empty value, bad model
# year). Silver flags the odd bad row; more than this means the source
# changed its format.
MAX_BAD_SHARE = 0.01

MONTH_YEAR = re.compile(r"^(\d{2})/(\d{4})$")
MODEL_YEAR = re.compile(r"^\d{4}$")

ATTEMPTS = 3
TIMEOUT_SECONDS = 300
USER_AGENT = "python-urllib open-data-ingestion/1.0"


class SourceError(Exception):
    """The portal did not deliver the data: network, HTTP or a cut download."""


class ValidationError(Exception):
    """The data arrived but fails the quality checks."""


# ---------------------------------------------------------------- download

def http_get(url, opener=urllib.request.urlopen):
    """GET with retries. Returns the body and the Last-Modified header."""
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read(), response.headers.get("Last-Modified")
        except (OSError, http.client.HTTPException) as error:  # URLError and timeouts are OSError
            last_error = error
            print(f"ingesta: attempt {attempt} of {ATTEMPTS} failed for {url}: {error}")
            if attempt < ATTEMPTS:
                time.sleep(2 ** attempt)
    raise SourceError(f"No answer from {url} after {ATTEMPTS} attempts: {last_error}")


def download(opener=urllib.request.urlopen):
    """Download the whole dataset as CSV text with the column names of the source.

    Asks the portal how many rows it has and requests them all at once,
    so a cut download shows up as a count that does not match.
    """
    body, _ = http_get(f"{RESOURCE_URL}.json?" + urllib.parse.urlencode({"$select": "count(*)"}), opener)
    try:
        expected_rows = int(json.loads(body)[0]["count"])
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise SourceError(f"The portal did not report its row count: {body[:200]!r}") from error

    body, last_modified = http_get(f"{RESOURCE_URL}.csv?" + urllib.parse.urlencode({"$limit": expected_rows}), opener)
    header, _, rows = body.partition(b"\n")
    try:
        fields = next(csv.reader([header.decode("utf-8")]))
    except (UnicodeDecodeError, StopIteration) as error:
        raise SourceError(f"The portal did not send a CSV header: {header[:200]!r}") from error
    # A field this pipeline does not know keeps its API name; a missing one
    # is reported by the columnas check of validate()
    names = io.StringIO()
    csv.writer(names, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow([FIELDS.get(f, f) for f in fields])
    data = names.getvalue().encode("utf-8") + rows
    return data, {"filas_en_portal": expected_rows, "ultima_modificacion_fuente": last_modified}


# -------------------------------------------------------------- validation

def validate(data, expected_rows=None, today=None):
    """Run the quality checks on the CSV bytes.

    Returns (checks, profile). Each check is a dict with nombre, ok and
    detalle. Nothing is raised here: the caller decides what a failure means.
    """
    today = today or datetime.date.today()
    checks = []

    def check(name, ok, detail):
        checks.append({"nombre": name, "ok": bool(ok), "detalle": detail})

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        check("codificacion", False, f"El archivo no es UTF-8: {error}")
        return checks, {}
    reader = csv.reader(io.StringIO(text, newline=""))
    header = [h.strip() for h in next(reader, [])]

    missing = [c for c in COLUMNS if c not in header]
    extra = [c for c in header if c not in COLUMNS]
    check("columnas", not missing and not extra,
          f"faltan {missing}, sobran {extra}" if missing or extra
          else f"las {len(COLUMNS)} columnas esperadas estan")
    if missing:
        return checks, {"columnas": header}

    index = {name: header.index(name) for name in COLUMNS}
    rows = 0
    wrong_width = 0
    empty = {name: 0 for name in COLUMNS}
    bad_dates = 0
    out_of_range = 0
    bad_models = 0
    unknown_severity = 0
    months = set()
    for row in reader:
        rows += 1
        if len(row) != len(header):
            wrong_width += 1
            continue
        for name in COLUMNS:
            if not row[index[name]].strip():
                empty[name] += 1
        match = MONTH_YEAR.match(row[index["FECHA_ACCIDENTE"]].strip())
        if not match or not 1 <= int(match.group(1)) <= 12:
            bad_dates += 1
        else:
            month, year = int(match.group(1)), int(match.group(2))
            if year < FIRST_YEAR or (year, month) > (today.year, today.month):
                out_of_range += 1
            else:
                months.add((year, month))
        if not MODEL_YEAR.match(row[index["MODELO_VEHICULO"]].strip()):
            bad_models += 1
        if row[index["GRAVEDAD_ACCIDENTE"]].strip().upper() not in SEVERITIES:
            unknown_severity += 1

    allowed = int(rows * MAX_BAD_SHARE)
    check("filas_minimas", rows >= MIN_ROWS, f"{rows} filas, minimo {MIN_ROWS}")
    if expected_rows is not None:
        check("filas_completas", rows == expected_rows,
              f"{rows} filas descargadas, el portal reporta {expected_rows}")
    check("filas_bien_formadas", wrong_width == 0,
          f"{wrong_width} filas con un numero de columnas distinto a {len(header)}")
    check("vacios_razonables", max(empty.values()) <= allowed,
          f"vacios por columna {empty}, tolerancia {allowed} filas")
    # Dates and severity are the key of the analysis: no bad value is allowed
    check("fecha_mm_aaaa", bad_dates == 0, f"{bad_dates} fechas que no siguen el formato MM/AAAA")
    check("fecha_en_rango", out_of_range == 0,
          f"{out_of_range} fechas antes de {FIRST_YEAR} o despues de {today.strftime('%m/%Y')}")
    check("gravedad_dos_valores", unknown_severity == 0,
          f"{unknown_severity} filas con gravedad fuera de {sorted(SEVERITIES)}")
    check("modelo_anio_valido", bad_models <= allowed,
          f"{bad_models} modelos que no son un año de 4 digitos, tolerancia {allowed} filas")

    profile = {
        "filas": rows,
        "columnas": header,
        "vacios": empty,
        "meses": len(months),
        "mes_minimo": "%04d-%02d" % min(months) if months else None,
        "mes_maximo": "%04d-%02d" % max(months) if months else None,
    }
    return checks, profile


def failed(checks):
    return [c for c in checks if not c["ok"]]


# ----------------------------------------------------------------- storage

class LocalStore:
    """Files under a folder of this machine."""

    def __init__(self, root):
        self.root = root

    def location(self, key):
        return f"{self.root}/{key}"

    def read(self, key):
        try:
            with open(self.location(key), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def write(self, key, data):
        path = self.location(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


class S3Store:
    """Objects under s3://bucket/prefix. Uses the role or keys of the environment."""

    def __init__(self, root, client=None):
        bucket, _, prefix = root[len("s3://"):].partition("/")
        self.root = root
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client or self._client()

    @staticmethod
    def _client():
        try:
            import boto3
            return boto3.client("s3")
        except ImportError:
            # Glue Python shell without the analytics library set only brings botocore
            import botocore.session
            return botocore.session.get_session().create_client("s3")

    def _key(self, key):
        return f"{self.prefix}/{key}" if self.prefix else key

    def location(self, key):
        return f"s3://{self.bucket}/{self._key(key)}"

    def read(self, key):
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None

    def write(self, key, data):
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)


def open_store(data_dir):
    data_dir = data_dir.rstrip("/")
    return S3Store(data_dir) if data_dir.startswith("s3://") else LocalStore(data_dir)


# ---------------------------------------------------------------- pipeline

def to_json(document):
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")


def ingest(store, opener=urllib.request.urlopen, now=None, use_backup=True, local_file=None):
    """Download (or read local_file), validate and publish. Returns the manifest written."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    day = now.date().isoformat()
    current_key = f"raw/{FILE_NAME}"

    manifest = {
        "fuente": "Vehiculos involucrados en un accidente de transito Ley 2251-2022, "
                  "Ministerio de Transporte - RUNT, datos.gov.co",
        "licencia": "CC BY-SA 4.0",
        "dataset_id": DATASET_ID,
        "url": f"{RESOURCE_URL}.csv",
        "ejecutado_en": now.isoformat(timespec="seconds"),
        "fecha_descarga": day,
    }

    if local_file:
        with open(local_file, "rb") as f:
            data = f.read()
        manifest["origen"] = "archivo_local"
        manifest["archivo_local"] = os.path.basename(local_file)
    else:
        try:
            data, source = download(opener)
            manifest.update(source)
            manifest["origen"] = "portal"
        except SourceError as error:
            if not use_backup:
                raise
            print(f"ingesta: WARNING the portal is not available, using the backup copy. {error}")
            backup_key = f"raw/respaldo/{FILE_NAME}"
            data = store.read(backup_key)
            if data is None:
                backup_key = current_key
                data = store.read(backup_key)
            if data is None:
                raise SourceError(f"{error}. There is no backup copy either in "
                                  f"{store.location(f'raw/respaldo/{FILE_NAME}')} or {store.location(current_key)}")
            manifest["origen"] = "respaldo"
            manifest["respaldo_usado"] = store.location(backup_key)
            manifest["error_fuente"] = str(error)

    checks, profile = validate(data, manifest.get("filas_en_portal"), now.date())
    manifest.update(profile)
    manifest["bytes"] = len(data)
    manifest["sha256"] = hashlib.sha256(data).hexdigest()
    manifest["validaciones"] = checks

    problems = failed(checks)
    if problems:
        rejected = f"raw/rechazados/fecha_ingesta={day}"
        store.write(f"{rejected}/{FILE_NAME}", data)
        store.write(f"{rejected}/manifiesto.json", to_json(manifest))
        raise ValidationError(describe(problems, checks, manifest["origen"])
                              + f"\nThe current raw copy was not replaced. The rejected file is in "
                                f"{store.location(rejected)}")

    previous = store.read("raw/manifiesto.json")
    previous_hash = json.loads(previous).get("sha256") if previous else None
    manifest["cambio_respecto_a_la_anterior"] = manifest["sha256"] != previous_hash
    manifest["ruta_vigente"] = store.location(current_key)

    # The current copy is rewritten only when its content differs, so a run
    # with an unchanged source leaves the file byte for byte as it was.
    current = store.read(current_key)
    if current is None or hashlib.sha256(current).hexdigest() != manifest["sha256"]:
        store.write(current_key, data)
    if manifest["cambio_respecto_a_la_anterior"]:
        snapshot = f"raw/historico/fecha_ingesta={day}"
        manifest["ruta_fechada"] = store.location(f"{snapshot}/{FILE_NAME}")
        store.write(f"{snapshot}/{FILE_NAME}", data)
        store.write(f"{snapshot}/manifiesto.json", to_json(manifest))
    else:
        manifest["ruta_fechada"] = json.loads(previous).get("ruta_fechada")
    store.write("raw/manifiesto.json", to_json(manifest))
    return manifest


def describe(problems, checks, origin):
    lines = "\n".join(f"  - {c['nombre']}: {c['detalle']}" for c in problems)
    return f"The data from {origin} failed {len(problems)} of {len(checks)} checks:\n{lines}"


def check_current(data):
    """Validate the current raw copy before the pipeline uses it. Raises ValidationError."""
    checks, profile = validate(data)
    problems = failed(checks)
    if problems:
        raise ValidationError(describe(problems, checks, "the current raw copy"))
    return profile


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ingest the source dataset into the raw zone of the lake")
    # Glue passes its arguments as --data_dir value
    parser.add_argument("--data-dir", "--data_dir", default=os.environ.get("DATA_DIR", "data"),
                        help="Root of the lake: a folder or s3://bucket (default: DATA_DIR or data)")
    parser.add_argument("--archivo", default=None,
                        help="Ingest this local CSV instead of downloading it from the portal")
    parser.add_argument("--sin-respaldo", "--sin_respaldo", action="store_true",
                        help="Fail if the portal does not answer instead of using the backup copy")
    args, _ = parser.parse_known_args(argv)

    store = open_store(args.data_dir)
    try:
        manifest = ingest(store, use_backup=not args.sin_respaldo, local_file=args.archivo)
    except (SourceError, ValidationError) as error:
        # Exits with code 1 and the message, which Glue shows as the job error
        raise SystemExit(f"ingesta: ERROR {error}")

    change = "new content" if manifest["cambio_respecto_a_la_anterior"] else "same content as the previous run"
    print(f"ingesta: {manifest['filas']} rows from {manifest['origen']}, "
          f"{len(manifest['validaciones'])} checks passed, {change}, "
          f"current copy in {manifest['ruta_vigente']}")


if __name__ == "__main__":
    main()
