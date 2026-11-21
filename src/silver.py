"""Silver layer: cleaning, typing and quality flags over bronze.

One row per vehicle involved in an accident with victims. Decisions:

- Identical rows are kept. The source has no accident id, day or place,
  so two vehicles of the same make, model, type, month and municipality
  produce the same row (two motorcycles in one crash, or two crashes in
  a month). Dropping them would delete real vehicles; their count is
  printed and reported in the EDA.
- Texts are stripped, upper cased and stripped of accents, so that
  "SECRETARÍA" and "SECRETARIA" are one authority.
- Brands with fewer than MIN_BRAND_ROWS rows go to "OTRAS" (marca_grupo)
  and vehicle types with fewer than MIN_TYPE_ROWS rows go to "OTRO"
  (tipo_grupo); the original values stay in marca and tipo.
- The municipality key is "MUNICIPIO (DEPARTAMENTO)": 663 names map to
  689 municipalities because some names repeat across departments.
- edad is the age at the accident, anio - modelo, floored at 0 (a model
  year can be sold the year before). EDAD_VEHICULO of the source is kept
  as edad_fuente but not used: it equals about (2027 - modelo) for all
  rows, that is, the age at the publication date, not at the accident,
  so it inflates the age of 2022 accidents by up to 4 years.
- Impossible values are flagged, not dropped: modelo_invalido when the
  model year is after anio + 1 or before 1950 (edad is left empty), and
  edad_fuente_invalida when EDAD_VEHICULO is empty or not a number.
- Reporting quality per municipality and month (coverage_flags): each
  month is compared with the median monthly count of that municipality
  in 2022-2024, months without rows counted as zero. A month below 20%
  of that median is a drop (alerta_caida) and one above 3 times the
  median is a bulk load (alerta_carga_masiva). Only municipalities with
  a median of at least 5 rows a month are judged; smaller ones swing too
  much by chance. Every vehicle carries cobertura_anomala from its
  municipality and month.
"""

import unicodedata

import numpy as np
import pandas as pd

from src import config

MIN_BRAND_ROWS = 200
MIN_TYPE_ROWS = 1000
OTHER_BRAND = "OTRAS"
OTHER_TYPE = "OTRO"

# Authority of the national police (DITRA): it covers roads in 645
# municipalities, unlike the municipal transit offices
NATIONAL_AUTHORITY = "DIRECCION DE TRANSITO Y TRANSPORTE"

VEHICLE_CLASS = {
    "MOTOCICLETA": "moto", "CICLOMOTOR": "moto", "MOTOCARRO": "moto", "MOTOTRICICLO": "moto",
    "CUATRIMOTO": "moto", "CUADRICICLO": "moto",
    "AUTOMOVIL": "liviano", "CAMIONETA": "liviano", "CAMPERO": "liviano",
    "BUS": "pasajeros", "BUSETA": "pasajeros", "MICROBUS": "pasajeros",
    "CAMION": "carga", "TRACTOCAMION": "carga", "VOLQUETA": "carga",
    "REMOLQUE": "carga", "SEMIREMOLQUE": "carga",
}
OTHER_CLASS = "maquinaria_otro"

REFERENCE_YEARS = (2022, 2024)
DROP_RATIO = 0.2
BULK_RATIO = 3.0
MIN_REFERENCE_MEDIAN = 5
SEED = 42


def normalize_text(series):
    """Strip, upper case, remove accents and repeated spaces."""
    def clean(value):
        value = unicodedata.normalize("NFKD", value)
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return " ".join(value.upper().split())

    uniques = series.fillna("").unique()
    return series.fillna("").map({v: clean(v) for v in uniques})


def group_rare(series, min_rows, other):
    counts = series.value_counts()
    keep = counts[counts >= min_rows].index
    return series.where(series.isin(keep), other)


def coverage_flags(df):
    """Full municipality x month grid with counts and reporting quality flags.

    Includes months with zero rows between the first and last month of
    the data, so that a drop to zero is visible.
    """
    months = pd.period_range(df["fecha"].min(), df["fecha"].max(), freq="M")
    places = df[["municipio", "municipio_nombre", "departamento"]].drop_duplicates("municipio")
    counts = (df.groupby(["municipio", "periodo"]).agg(registros=("con_muertos", "size"),
                                                         con_muertos=("con_muertos", "sum"))
              .reset_index())
    grid = pd.MultiIndex.from_product([places["municipio"], months.strftime("%Y-%m")],
                                      names=["municipio", "periodo"]).to_frame(index=False)
    grid = grid.merge(counts, on=["municipio", "periodo"], how="left").fillna({"registros": 0, "con_muertos": 0})
    grid[["registros", "con_muertos"]] = grid[["registros", "con_muertos"]].astype("int64")
    grid["anio"] = grid["periodo"].str[:4].astype("int64")
    grid["mes"] = grid["periodo"].str[5:].astype("int64")
    grid = grid.merge(places, on="municipio", how="left")

    first, last = REFERENCE_YEARS
    reference = (grid[grid["anio"].between(first, last)].groupby("municipio")["registros"].median()
                 .rename("mediana_referencia"))
    grid = grid.merge(reference, on="municipio", how="left")
    judged = grid["mediana_referencia"] >= MIN_REFERENCE_MEDIAN
    ratio = grid["registros"] / grid["mediana_referencia"].replace(0, np.nan)
    grid["razon_vs_referencia"] = ratio.round(4)
    grid["alerta_caida"] = (judged & (ratio < DROP_RATIO)).astype("int64")
    grid["alerta_carga_masiva"] = (judged & (ratio > BULK_RATIO)).astype("int64")
    grid["alerta_cobertura"] = grid["alerta_caida"] | grid["alerta_carga_masiva"]
    grid["municipio_evaluable"] = judged.astype("int64")
    return grid


def redistribute_bulk_loads(df):
    """Spread each bulk load over the months it most likely belongs to.

    A bulk load is a municipality-month above 3 times that municipality's
    2022-2024 median: late reports uploaded with a single date. That month
    keeps its typical count (the median, chosen at random with a fixed
    seed) and the excess is reassigned to the municipality's earlier months,
    from the start of the reference period (2022-01) to the month before the
    load, in proportion to what each month reported, never to a year earlier
    than the vehicle's model year minus one, so
    seasonality is preserved. Moved rows keep their published month in
    periodo_original and carry fecha_imputada = 1; they stay out of model
    training because their month is uncertain.
    """
    df["periodo_original"] = df["periodo"]
    df["fecha_imputada"] = 0
    grid = coverage_flags(df)
    rng = np.random.default_rng(SEED)
    first = f"{REFERENCE_YEARS[0]}-01"
    for row in grid[grid["alerta_carga_masiva"] == 1].itertuples():
        rows = df.index[(df["municipio"] == row.municipio) & (df["periodo"] == row.periodo)].to_numpy()
        keep = int(round(row.mediana_referencia))
        past = grid[(grid["municipio"] == row.municipio) & (grid["periodo"] >= first) & (grid["periodo"] < row.periodo)]
        if len(rows) <= keep or past["registros"].sum() == 0:
            continue
        move = rng.permutation(rows)[keep:]
        # A vehicle can only move to a month at least as recent as its model year
        # minus one (the same rule that flags impossible model years); vehicles
        # with no compatible month stay where they were published
        model_year = pd.to_numeric(df.loc[move, "MODELO_VEHICULO"].str.strip(), errors="coerce")
        min_year = (model_year - 1).fillna(0).astype(int).to_numpy()
        past_year = past["periodo"].str[:4].astype(int).to_numpy()
        for year in np.unique(min_year):
            group = move[min_year == year]
            ok = past_year >= year
            if not ok.any():
                continue
            counts = past["registros"].to_numpy()[ok]
            df.loc[group, "periodo"] = rng.choice(past["periodo"].to_numpy()[ok], size=len(group), p=counts / counts.sum())
            df.loc[group, "fecha_imputada"] = 1
    moved = df["fecha_imputada"] == 1
    df.loc[moved, "fecha"] = pd.to_datetime(df.loc[moved, "periodo"], format="%Y-%m")
    df["anio"] = df["fecha"].dt.year.astype("int64")
    df["mes"] = df["fecha"].dt.month.astype("int64")
    return df


def main():
    df = config.read_parquet(config.BRONZE)
    bronze_rows = len(df)
    source_columns = [c for c in df.columns if c not in ("anio", "id_registro")]
    identical = int(df.duplicated(subset=source_columns).sum())

    out = pd.DataFrame(index=df.index)
    out["id_registro"] = df["id_registro"]
    out["marca"] = normalize_text(df["MARCA_VEHICULO"])
    out["marca_grupo"] = group_rare(out["marca"], MIN_BRAND_ROWS, OTHER_BRAND)
    out["tipo"] = normalize_text(df["TIPO_VEHICULO"])
    out["tipo_grupo"] = group_rare(out["tipo"], MIN_TYPE_ROWS, OTHER_TYPE)
    out["clase_vehiculo"] = out["tipo"].map(VEHICLE_CLASS).fillna(OTHER_CLASS)
    out["departamento"] = normalize_text(df["DEPARTAMENTO_ACCIDENTE"])
    out["municipio_nombre"] = normalize_text(df["MUNICIPIO_ACCIDENTE"])
    out["municipio"] = out["municipio_nombre"] + " (" + out["departamento"] + ")"
    out["autoridad"] = normalize_text(df["AUTORIDAD_DE_TRANSITO"])
    out["autoridad_nacional"] = (out["autoridad"] == NATIONAL_AUTHORITY).astype("int64")

    date_text = df["FECHA_ACCIDENTE"].str.strip()
    out["fecha"] = pd.to_datetime(date_text, format="%m/%Y")
    out["anio"] = out["fecha"].dt.year.astype("int64")
    out["mes"] = out["fecha"].dt.month.astype("int64")
    out["periodo"] = out["fecha"].dt.strftime("%Y-%m")

    gravedad = normalize_text(df["GRAVEDAD_ACCIDENTE"])
    out["gravedad"] = gravedad
    out["con_muertos"] = (gravedad == "CON MUERTOS").astype("int64")
    # Bulk loads are spread before anything that depends on the date (vehicle age, flags)
    out["MODELO_VEHICULO"] = df["MODELO_VEHICULO"]
    out = redistribute_bulk_loads(out).drop(columns="MODELO_VEHICULO")

    modelo = pd.to_numeric(df["MODELO_VEHICULO"].str.strip(), errors="coerce")
    out["modelo_invalido"] = (modelo.isna() | (modelo > out["anio"] + 1) | (modelo < 1950)).astype("int64")
    out["modelo"] = modelo.where(out["modelo_invalido"] == 0).astype("Int64")
    out["edad"] = (out["anio"] - out["modelo"]).clip(lower=0).astype("Float64")
    # Source age, as published: empty and malformed values such as "2,020" become empty
    edad_fuente = pd.to_numeric(df["EDAD_VEHICULO"].str.strip(), errors="coerce")
    out["edad_fuente_invalida"] = (edad_fuente.isna() | (edad_fuente > 100)).astype("int64")
    out["edad_fuente"] = edad_fuente.where(out["edad_fuente_invalida"] == 0).astype("Float64")

    grid = coverage_flags(out)
    flags = grid[["municipio", "periodo", "alerta_cobertura"]].rename(columns={"alerta_cobertura": "cobertura_anomala"})
    out = out.merge(flags, on=["municipio", "periodo"], how="left")
    # Rows with an imputed month stay out of training like anomalous months
    out["cobertura_anomala"] = (out["cobertura_anomala"] | out["fecha_imputada"]).astype("int64")

    config.prepare(config.SILVER)
    config.write_parquet(out, config.SILVER, partition_cols=["anio"])
    print(f"silver: {bronze_rows} rows in bronze, {identical} identical rows kept (no accident id), "
          f"{int(out['modelo_invalido'].sum())} impossible model years, "
          f"{int(out['edad_fuente_invalida'].sum())} invalid source ages, "
          f"{int(out['fecha_imputada'].sum())} rows of bulk loads spread over earlier months, "
          f"{int(out['cobertura_anomala'].sum())} rows in anomalous municipality-months, "
          f"{len(out)} rows written to {config.SILVER}")


if __name__ == "__main__":
    main()
