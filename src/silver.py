"""Capa silver: limpieza, tipado y validacion de la capa bronze.

Deja una fila por registro, con fechas y horas en tipos correctos,
coordenadas numericas y columnas con nombres simples. Quita los
duplicados exactos y las filas que no pasan las validaciones.
"""

import pandas as pd

from src import config

NOMBRES = {
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

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

FRANJAS = {
    (0, 5): "madrugada",
    (6, 11): "manana",
    (12, 17): "tarde",
    (18, 23): "noche",
}

GRAVEDADES = ["SOLO DAÑOS", "HERIDOS", "MUERTOS"]


def parsear_fecha(serie):
    """Une los dos formatos de fecha que trae la fuente."""
    iso = serie.str.contains("T")
    fechas = pd.Series(pd.NaT, index=serie.index)
    fechas[iso] = pd.to_datetime(serie[iso].str[:10], format="%Y-%m-%d", errors="coerce")
    fechas[~iso] = pd.to_datetime(serie[~iso], format="%d/%m/%Y", errors="coerce")
    return fechas


def parsear_hora(serie):
    """Une los dos formatos de hora: 12 horas con a. m. y p. m., e ISO."""
    iso = serie.str.contains("T")
    horas = pd.Series(pd.NaT, index=serie.index)
    horas[iso] = pd.to_datetime(serie[iso].str[11:19], format="%H:%M:%S", errors="coerce")
    limpia = serie[~iso].str.strip().str.replace("a. m.", "AM").str.replace("p. m.", "PM")
    horas[~iso] = pd.to_datetime(limpia, format="%I:%M:%S %p", errors="coerce")
    return horas


def asignar_franja(hora):
    for (inicio, fin), nombre in FRANJAS.items():
        if inicio <= hora <= fin:
            return nombre
    return None


def extraer_coordenadas(serie):
    """Saca longitud y latitud del texto POINT (lon lat)."""
    partes = serie.str.extract(r"POINT \((-?\d+\.?\d*) (-?\d+\.?\d*)\)")
    lon = pd.to_numeric(partes[0], errors="coerce")
    lat = pd.to_numeric(partes[1], errors="coerce")
    fuera = ~lon.between(-75.8, -75.4) | ~lat.between(6.0, 6.3)
    lon[fuera] = None
    lat[fuera] = None
    return lon, lat


def main():
    df = pd.read_parquet(config.BRONZE)
    filas_bronze = len(df)

    duplicados = df.duplicated(subset=[c for c in df.columns if c != "año"])
    df = df[~duplicados].copy()

    df = df.rename(columns=NOMBRES)

    df["fecha"] = parsear_fecha(df["fecha_texto"])
    hora = parsear_hora(df["hora_texto"])
    df["hora"] = hora.dt.hour
    df["fecha_hora"] = df["fecha"] + pd.to_timedelta(hora.dt.strftime("%H:%M:%S"))

    df["año"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["dia_semana"] = df["fecha"].dt.weekday.map(dict(enumerate(DIAS)))
    df["franja"] = df["hora"].map(asignar_franja)
    df["lon"], df["lat"] = extraer_coordenadas(df["coordenadas"])

    for col in ["clase_accidente", "causa", "barrio", "area", "gravedad"]:
        df[col] = df[col].str.strip()

    validas = df["fecha"].notna() & df["hora"].notna() & df["gravedad"].isin(GRAVEDADES)
    invalidas = int((~validas).sum())
    df = df[validas]

    columnas = [
        "radicado", "fecha_hora", "fecha", "año", "mes", "dia_semana", "hora",
        "franja", "gravedad", "clase_accidente", "causa", "barrio", "area",
        "clase_vehiculo", "tipo_servicio", "tipo_victima", "sexo",
        "direccion", "lon", "lat",
    ]
    df = df[columnas]

    config.preparar(config.SILVER)
    df.to_parquet(config.SILVER, index=False, partition_cols=["año"])
    print(f"silver: {filas_bronze} filas en bronze, {int(duplicados.sum())} duplicados, "
          f"{invalidas} invalidas, {len(df)} filas escritas en {config.SILVER}")


if __name__ == "__main__":
    main()
