"""Gold layer: the three analytic tables of the base document.

    gold/vehiculos/anio=YYYY/   one row per vehicle (id_registro): model features and target con_muertos
    gold/municipio_mes/         municipality x month: counts, share with deaths, quality flags (dashboard)
    gold/municipio/             one row per municipality: features for clustering

Gold is what Athena (and the dashboard) reads, so names are plain ASCII
and each table lives in its own folder. Shares are proportions in [0, 1]
and carry the prefix prop_.
"""

from src import config
from src.silver import coverage_flags

MIN_ROWS_CLUSTERING = 100

VEHICLE_COLUMNS = [
    "id_registro", "periodo", "mes", "departamento", "municipio", "municipio_nombre", "autoridad", "autoridad_nacional",
    "tipo", "tipo_grupo", "clase_vehiculo", "marca", "marca_grupo", "modelo", "edad",
    "modelo_invalido", "cobertura_anomala", "fecha_imputada", "periodo_original", "con_muertos", "anio",
]


def build_municipality_month(silver):
    grid = coverage_flags(silver)
    # Bulk loads were spread in silver: keep track of what moved and keep the
    # original month flagged, so the dashboard can still show it
    moved = silver[silver["fecha_imputada"] == 1]
    moved_in = moved.groupby(["municipio", "periodo"]).size().rename("registros_reubicados_hacia")
    moved_out = moved.groupby(["municipio", "periodo_original"]).size().rename("registros_reubicados_desde")
    moved_out.index = moved_out.index.set_names(["municipio", "periodo"])
    grid = (grid.merge(moved_in, on=["municipio", "periodo"], how="left")
                .merge(moved_out, on=["municipio", "periodo"], how="left")
                .fillna({"registros_reubicados_hacia": 0, "registros_reubicados_desde": 0}))
    grid[["registros_reubicados_hacia", "registros_reubicados_desde"]] = grid[["registros_reubicados_hacia", "registros_reubicados_desde"]].astype("int64")
    grid["registros_publicados"] = grid["registros"] - grid["registros_reubicados_hacia"] + grid["registros_reubicados_desde"]
    grid["alerta_carga_masiva"] = (grid["alerta_carga_masiva"] | (grid["registros_reubicados_desde"] > 0)).astype("int64")
    grid["alerta_cobertura"] = (grid["alerta_caida"] | grid["alerta_carga_masiva"]).astype("int64")
    grid["prop_con_muertos"] = (grid["con_muertos"] / grid["registros"].where(grid["registros"] > 0)).round(4)
    columns = ["municipio", "municipio_nombre", "departamento", "anio", "mes", "periodo", "registros",
               "registros_publicados", "registros_reubicados_desde", "registros_reubicados_hacia",
               "con_muertos", "prop_con_muertos", "mediana_referencia", "razon_vs_referencia",
               "municipio_evaluable", "alerta_caida", "alerta_carga_masiva", "alerta_cobertura"]
    return grid[columns].sort_values(["municipio", "periodo"]).reset_index(drop=True)


def build_municipality(silver, month_table):
    silver = silver.assign(es_moto=(silver["clase_vehiculo"] == "moto").astype(int),
                           es_carga=(silver["clase_vehiculo"] == "carga").astype(int))
    table = silver.groupby(["municipio", "municipio_nombre", "departamento"], as_index=False).agg(
        registros=("con_muertos", "size"),
        con_muertos=("con_muertos", "sum"),
        prop_con_muertos=("con_muertos", "mean"),
        edad_promedio=("edad", "mean"),
        prop_motos=("es_moto", "mean"),
        prop_carga=("es_carga", "mean"),
        prop_autoridad_nacional=("autoridad_nacional", "mean"),
        primer_periodo=("periodo", "min"),
        ultimo_periodo=("periodo", "max"),
    )
    months = month_table.groupby("municipio").agg(meses_con_registros=("registros", lambda s: int((s > 0).sum())),
                                                  meses_alerta_cobertura=("alerta_cobertura", "sum"))
    table = table.merge(months, on="municipio", how="left")
    table["apto_agrupamiento"] = (table["registros"] >= MIN_ROWS_CLUSTERING).astype("int64")
    for col in ["prop_con_muertos", "edad_promedio", "prop_motos", "prop_carga", "prop_autoridad_nacional"]:
        table[col] = table[col].astype(float).round(4)
    return table.sort_values("registros", ascending=False).reset_index(drop=True)


def main():
    silver = config.read_parquet(config.SILVER)
    silver["anio"] = silver["anio"].astype("int64")

    vehicles = silver[VEHICLE_COLUMNS]
    config.prepare(config.GOLD_VEHICULOS)
    config.write_parquet(vehicles, config.GOLD_VEHICULOS, partition_cols=["anio"])

    month_table = build_municipality_month(silver)
    config.prepare(config.GOLD_MUNICIPIO_MES)
    config.write_parquet(month_table, f"{config.GOLD_MUNICIPIO_MES}/municipio_mes.parquet")

    municipalities = build_municipality(silver, month_table)
    config.prepare(config.GOLD_MUNICIPIO)
    config.write_parquet(municipalities, f"{config.GOLD_MUNICIPIO}/municipio.parquet")

    print(f"gold: {len(vehicles)} vehicles, {len(month_table)} municipality-months "
          f"({int(month_table['alerta_cobertura'].sum())} with a coverage alert), "
          f"{len(municipalities)} municipalities ({int(municipalities['apto_agrupamiento'].sum())} with "
          f">= {MIN_ROWS_CLUSTERING} rows)")


if __name__ == "__main__":
    main()
