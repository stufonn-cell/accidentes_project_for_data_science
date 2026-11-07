"""Capa gold: tabla de siniestros y agregados listos para el tablero.

Construye una fila por siniestro a partir de la capa silver, con la
gravedad mas alta entre sus registros, y los agregados que consumen
el tablero y los modelos.
"""

import pandas as pd

from src import config

ORDEN_GRAVEDAD = {"SOLO DAÑOS": 0, "HERIDOS": 1, "MUERTOS": 2}


def construir_siniestros(df):
    df = df.sort_values("fecha_hora")
    df["nivel_gravedad"] = df["gravedad"].map(ORDEN_GRAVEDAD)

    siniestros = df.groupby("radicado", as_index=False).agg(
        fecha_hora=("fecha_hora", "first"),
        fecha=("fecha", "first"),
        año=("año", "first"),
        mes=("mes", "first"),
        dia_semana=("dia_semana", "first"),
        hora=("hora", "first"),
        franja=("franja", "first"),
        clase_accidente=("clase_accidente", "first"),
        causa=("causa", "first"),
        barrio=("barrio", "first"),
        area=("area", "first"),
        nivel_gravedad=("nivel_gravedad", "max"),
        registros=("radicado", "size"),
        lon=("lon", "first"),
        lat=("lat", "first"),
    )
    inverso = {v: k for k, v in ORDEN_GRAVEDAD.items()}
    siniestros["gravedad"] = siniestros["nivel_gravedad"].map(inverso)
    siniestros["con_victimas"] = (siniestros["nivel_gravedad"] >= 1).astype(int)
    return siniestros.drop(columns="nivel_gravedad")


def construir_agregados(siniestros):
    tablas = {}

    tablas["por_mes"] = (
        siniestros.groupby(["año", "mes"], as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
    )
    tablas["por_barrio"] = (
        siniestros.groupby("barrio", as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"),
             muertos=("gravedad", lambda s: int((s == "MUERTOS").sum())))
        .sort_values("siniestros", ascending=False)
    )
    tablas["por_dia_hora"] = (
        siniestros.groupby(["dia_semana", "hora"], as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
    )
    tablas["por_clase"] = (
        siniestros.groupby("clase_accidente", as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
        .sort_values("siniestros", ascending=False)
    )
    tablas["por_causa"] = (
        siniestros.groupby("causa", as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
        .sort_values("siniestros", ascending=False)
    )
    tablas["por_gravedad_año"] = (
        siniestros.groupby(["año", "gravedad"], as_index=False)
        .agg(siniestros=("radicado", "size"))
    )
    return tablas


def main():
    df = pd.read_parquet(config.SILVER)
    df["año"] = df["año"].astype(int)

    siniestros = construir_siniestros(df)
    config.preparar(config.GOLD_SINIESTROS)
    siniestros.to_parquet(config.GOLD_SINIESTROS, index=False, partition_cols=["año"])

    tablas = construir_agregados(siniestros)
    config.preparar(config.GOLD_AGREGADOS)
    for nombre, tabla in tablas.items():
        tabla.to_parquet(f"{config.GOLD_AGREGADOS}/{nombre}.parquet", index=False)

    print(f"gold: {len(siniestros)} siniestros y {len(tablas)} agregados escritos")


if __name__ == "__main__":
    main()
