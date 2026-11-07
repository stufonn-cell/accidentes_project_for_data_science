"""Silver layer: cleaning, typing and validation of the bronze layer.

Keeps one row per record, with dates and times in proper types, numeric
coordinates and simple column names. Drops exact duplicates and rows
that fail validation. Column names stay in Spanish because the data and
the dashboard are in Spanish.
"""

import pandas as pd

from src import config

COLUMN_NAMES = {
    "RADICADO": "radicado",
    "FECHA": "fecha_texto",
    "HORA": "hora_texto",
    "CLASE DE VEHICULO": "clase_vehiculo",
    "TIPO DE SERVICIO": "tipo_servicio",
    "TIPO DE VICTIMA": "tipo_victima",
    "SEXO": "sexo",
    "GRAVEDAD": "gravedad",
    "CLASE DE ACCIDENTE": "clase_accidente",
    "CAUSA": "causa",
    "DIRECCIÓN": "direccion",
    "BARRIO": "barrio",
    "AREA": "area",
    "Coordenadas": "coordenadas",
}

DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

TIME_SLOTS = {
    (0, 5): "madrugada",
    (6, 11): "manana",
    (12, 17): "tarde",
    (18, 23): "noche",
}

SEVERITIES = ["SOLO DAÑOS", "HERIDOS", "MUERTOS"]


def parse_date(series):
    """Merge the two date formats of the source."""
    iso = series.str.contains("T")
    dates = pd.Series(pd.NaT, index=series.index)
    dates[iso] = pd.to_datetime(series[iso].str[:10], format="%Y-%m-%d", errors="coerce")
    dates[~iso] = pd.to_datetime(series[~iso], format="%d/%m/%Y", errors="coerce")
    return dates


def parse_time(series):
    """Merge the two time formats: 12 hour with a. m. and p. m., and ISO."""
    iso = series.str.contains("T")
    times = pd.Series(pd.NaT, index=series.index)
    times[iso] = pd.to_datetime(series[iso].str[11:19], format="%H:%M:%S", errors="coerce")
    cleaned = series[~iso].str.strip().str.replace("a. m.", "AM").str.replace("p. m.", "PM")
    times[~iso] = pd.to_datetime(cleaned, format="%I:%M:%S %p", errors="coerce")
    return times


def assign_time_slot(hour):
    for (start, end), name in TIME_SLOTS.items():
        if start <= hour <= end:
            return name
    return None


def extract_coordinates(series):
    """Take longitude and latitude from the POINT (lon lat) text."""
    parts = series.str.extract(r"POINT \((-?\d+\.?\d*) (-?\d+\.?\d*)\)")
    lon = pd.to_numeric(parts[0], errors="coerce")
    lat = pd.to_numeric(parts[1], errors="coerce")
    outside = ~lon.between(-75.8, -75.4) | ~lat.between(6.0, 6.3)
    lon[outside] = None
    lat[outside] = None
    return lon, lat


def main():
    df = pd.read_parquet(config.BRONZE)
    bronze_rows = len(df)

    duplicates = df.duplicated(subset=[c for c in df.columns if c != "año"])
    df = df[~duplicates].copy()

    df = df.rename(columns=COLUMN_NAMES)

    df["fecha"] = parse_date(df["fecha_texto"])
    time = parse_time(df["hora_texto"])
    df["hora"] = time.dt.hour
    df["fecha_hora"] = df["fecha"] + pd.to_timedelta(time.dt.strftime("%H:%M:%S"))

    df["año"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["dia_semana"] = df["fecha"].dt.weekday.map(dict(enumerate(DAYS)))
    df["franja"] = df["hora"].map(assign_time_slot)
    df["lon"], df["lat"] = extract_coordinates(df["coordenadas"])

    for col in ["clase_accidente", "causa", "barrio", "area", "gravedad"]:
        df[col] = df[col].str.strip()

    valid = df["fecha"].notna() & df["hora"].notna() & df["gravedad"].isin(SEVERITIES)
    invalid = int((~valid).sum())
    df = df[valid]

    columns = [
        "radicado", "fecha_hora", "fecha", "año", "mes", "dia_semana", "hora",
        "franja", "gravedad", "clase_accidente", "causa", "barrio", "area",
        "clase_vehiculo", "tipo_servicio", "tipo_victima", "sexo",
        "direccion", "lon", "lat",
    ]
    df = df[columns]

    config.prepare(config.SILVER)
    df.to_parquet(config.SILVER, index=False, partition_cols=["año"])
    print(f"silver: {bronze_rows} rows in bronze, {int(duplicates.sum())} duplicates, "
          f"{invalid} invalid, {len(df)} rows written to {config.SILVER}")


if __name__ == "__main__":
    main()
