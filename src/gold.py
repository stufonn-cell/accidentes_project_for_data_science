"""Gold layer: accident table and aggregates ready for the dashboard.

Builds one row per accident from the silver layer, keeping the highest
severity among its records, plus the aggregates consumed by the
dashboard and the models.

Gold is what Power BI reads through Athena, so its names are plain ASCII:
the year column is `anio` instead of `año`, and every aggregate goes in
its own folder because Athena maps one folder to one table.
"""

from src import config

SEVERITY_ORDER = {"SOLO DAÑOS": 0, "HERIDOS": 1, "MUERTOS": 2}


def build_accidents(df):
    df = df.sort_values("fecha_hora")
    df["nivel_gravedad"] = df["gravedad"].map(SEVERITY_ORDER)

    accidents = df.groupby("radicado", as_index=False).agg(
        fecha_hora=("fecha_hora", "first"),
        fecha=("fecha", "first"),
        anio=("año", "first"),
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
    inverse = {v: k for k, v in SEVERITY_ORDER.items()}
    accidents["gravedad"] = accidents["nivel_gravedad"].map(inverse)
    accidents["con_victimas"] = (accidents["nivel_gravedad"] >= 1).astype(int)
    return accidents.drop(columns="nivel_gravedad")


def build_aggregates(accidents):
    tables = {}

    tables["por_mes"] = (
        accidents.groupby(["anio", "mes"], as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
    )
    tables["por_barrio"] = (
        accidents.groupby("barrio", as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"),
             muertos=("gravedad", lambda s: int((s == "MUERTOS").sum())))
        .sort_values("siniestros", ascending=False)
    )
    tables["por_dia_hora"] = (
        accidents.groupby(["dia_semana", "hora"], as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
    )
    tables["por_clase"] = (
        accidents.groupby("clase_accidente", as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
        .sort_values("siniestros", ascending=False)
    )
    tables["por_causa"] = (
        accidents.groupby("causa", as_index=False)
        .agg(siniestros=("radicado", "size"), con_victimas=("con_victimas", "sum"))
        .sort_values("siniestros", ascending=False)
    )
    tables["por_gravedad_anio"] = (
        accidents.groupby(["anio", "gravedad"], as_index=False)
        .agg(siniestros=("radicado", "size"))
    )
    return tables


def main():
    df = config.read_parquet(config.SILVER)
    df["año"] = df["año"].astype(int)

    accidents = build_accidents(df)
    config.prepare(config.GOLD_SINIESTROS)
    config.write_parquet(accidents, config.GOLD_SINIESTROS, partition_cols=["anio"])

    tables = build_aggregates(accidents)
    config.prepare(config.GOLD_AGREGADOS)
    for name, table in tables.items():
        config.write_parquet(table, f"{config.GOLD_AGREGADOS}/{name}/{name}.parquet")

    print(f"gold: {len(accidents)} accidents and {len(tables)} aggregates written")


if __name__ == "__main__":
    main()
