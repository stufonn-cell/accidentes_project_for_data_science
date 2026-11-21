"""Exports the gold layer to dashboard/data/datos.js for the web dashboard.

    python scripts/exportar_tablero_runt.py

Run it after `python -m src.pipeline`. The dashboard shows the same processed
tables the pipeline writes (locally or on S3), not the raw CSV: vehicle age
recomputed at the accident year, the municipality key with its department
and the coverage flags of each municipality-month.

What it writes:
- a cube by year, city and vehicle type for the map, on the same rows;
- a cube by month, department, vehicle type and age band, without the
  municipality-months flagged for anomalous reporting (the same rows the
  model trains on), for the findings section and its filters;
- the reporting audit: records per month for Medellin, Bogota and the rest
  of the country, and the coverage status of the 20 municipalities with
  most records;
- the model outputs (2024 temporal test, observed vs expected lethality,
  clusters and a sensitivity check with and without Medellin).
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402

RAW_CSV = ROOT / "data" / "raw" / "vehiculos_siniestros_runt.csv"
MANIFEST = ROOT / "data" / "raw" / "manifiesto.json"
OUT = ROOT / "dashboard" / "data" / "datos.js"
MODELS = ROOT / "data" / "gold" / "modelos"
TEMPORAL_TEST = "temporal_2024"
LETHALITY_MIN_ROWS = 1000
LETHALITY_TOP = 15
AGE_BANDS = [(0, 2, "0 a 2"), (3, 5, "3 a 5"), (6, 10, "6 a 10"), (11, 15, "11 a 15"), (16, 20, "16 a 20"), (21, 200, "21 o más")]
MIN_TYPE_ROWS = 1000
TOP_MUNICIPALITIES = 20
MEDELLIN = "MEDELLIN (ANTIOQUIA)"
BOGOTA = "BOGOTA (BOGOTA D.C.)"
# Coverage status of a municipality-month, as the pipeline flags it
NORMAL, DROP, BULK = 0, 1, 2


def age_band(age):
    if pd.isna(age):
        return len(AGE_BANDS)  # "sin dato", skipped by the age chart
    for i, (low, high, _) in enumerate(AGE_BANDS):
        if low <= age <= high:
            return i
    return len(AGE_BANDS) - 1


def model_section():
    """Model outputs for the dashboard, or None when the pipeline has not run."""
    needed = [MODELS / "metricas.json", MODELS / "metricas", MODELS / "letalidad", MODELS / "grupos", MODELS / "predicciones"]
    if not all(p.exists() for p in needed):
        return None
    description = json.loads((MODELS / "metricas.json").read_text(encoding="utf-8"))
    metrics = pd.read_parquet(MODELS / "metricas")
    metrics = metrics[metrics["evaluacion"] == TEMPORAL_TEST]
    lethality = pd.read_parquet(MODELS / "letalidad")
    lethality = lethality[lethality["registros"] >= LETHALITY_MIN_ROWS]
    lethality = lethality.reindex(lethality["diferencia"].abs().sort_values(ascending=False).index)
    groups = pd.read_parquet(MODELS / "grupos")
    summary = (groups.groupby("grupo")
               .agg(municipios=("municipio", "size"), registros=("registros", "sum"),
                    prop_con_muertos=("prop_con_muertos", "mean"),
                    prop_autoridad_nacional=("prop_autoridad_nacional", "mean"))
               .reset_index().sort_values("grupo"))
    # Sensitivity: out-of-fold scores of the grouped validation, with and without Medellin
    preds = pd.read_parquet(MODELS / "predicciones")
    oof = preds[(preds["origen"] == "fuera_de_pliegue_2022_2024") & (preds["cobertura_anomala"] == 0)]
    sensitivity = []
    for name, rows in [("todos", oof), ("sin_medellin", oof[oof["municipio"] != MEDELLIN]),
                       ("solo_medellin", oof[oof["municipio"] == MEDELLIN])]:
        sensitivity.append({"conjunto": name, "registros": len(rows),
                            "prevalencia": round(float(rows["con_muertos"].mean()), 4),
                            "pr_auc": round(float(average_precision_score(rows["con_muertos"], rows["probabilidad"])), 4)})
    # Coverage: share of fatal records found when the riskiest x % of records are reviewed
    # first, on the same out-of-fold scores (municipalities the model did not see)
    ordered = oof.sort_values("probabilidad", ascending=False)["con_muertos"].to_numpy()
    coverage = [{"fraccion": f, "recall": round(float(ordered[:int(round(len(ordered) * f))].sum() / ordered.sum()), 4)}
                for f in (0.1, 0.2, 0.3)]
    return {
        "version": description.get("version"),
        "mejor": description.get("mejor_modelo"),
        "umbral": description.get("umbral_decision"),
        "metricas": [{"modelo": r.modelo, "pr_auc": round(float(r.average_precision), 4),
                      "roc_auc": round(float(r.roc_auc), 4), "recall": round(float(r.recall), 4),
                      "precision": round(float(r.precision), 4), "mejor": int(r.es_mejor),
                      "prevalencia": round(float(r.prevalencia_prueba), 4)}
                     for r in metrics.itertuples()],
        "letalidad": [{"municipio": r.municipio, "registros": int(r.registros),
                       "observada": float(r.observada), "esperada": float(r.esperada),
                       "diferencia": float(r.diferencia), "razon": float(r.razon)}
                      for r in lethality.head(LETHALITY_TOP).itertuples()],
        "letalidad_min_registros": LETHALITY_MIN_ROWS,
        "grupos": [{"grupo": int(r.grupo), "municipios": int(r.municipios), "registros": int(r.registros),
                    "prop_con_muertos": round(float(r.prop_con_muertos), 4),
                    "prop_autoridad_nacional": round(float(r.prop_autoridad_nacional), 4)}
                   for r in summary.itertuples()],
        "sensibilidad": sensitivity,
        "cobertura": coverage,
    }


def main():
    vehicles = config.read_parquet(config.GOLD_VEHICULOS)
    vehicles["anio"] = vehicles["anio"].astype(int)
    months = sorted(vehicles["periodo"].unique())
    month_index = {m: i for i, m in enumerate(months)}
    vehicles["m"] = vehicles["periodo"].map(month_index)

    # Findings: only rows outside anomalous municipality-months
    clean = vehicles[vehicles["cobertura_anomala"] == 0].copy()
    counts = clean["tipo"].value_counts()
    shown = [t for t in counts.index if counts[t] >= MIN_TYPE_ROWS]
    clean["tipo_tablero"] = clean["tipo"].where(clean["tipo"].isin(shown), "OTROS")
    types = shown + ["OTROS"]
    type_class = clean.groupby("tipo")["clase_vehiculo"].first().to_dict()
    depts = sorted(vehicles["departamento"].unique())
    clean["d"] = clean["departamento"].map({v: i for i, v in enumerate(depts)})
    clean["t"] = clean["tipo_tablero"].map({v: i for i, v in enumerate(types)})
    clean["e"] = clean["edad"].map(age_band)
    cube = (clean.groupby(["m", "d", "t", "e"]).agg(n=("con_muertos", "size"), k=("con_muertos", "sum"))
            .reset_index().astype(int).values.tolist())
    # Map: the same clean rows by year, city and vehicle type. Sub-municipal transit
    # offices ("CALI - LOS CERROS (VALLE DEL CAUCA)") are added to their municipality.
    clean["ciudad"] = clean["municipio"].str.replace(r" - .*( \([^()]*\))$", r"\1", regex=True)
    cities = sorted(clean["ciudad"].unique())
    city_dept = clean.groupby("ciudad")["d"].first().reindex(cities).astype(int).tolist()
    clean["c"] = clean["ciudad"].map({v: i for i, v in enumerate(cities)})
    city_cube = (clean.groupby(["anio", "c", "t"]).agg(n=("con_muertos", "size"), k=("con_muertos", "sum"))
                 .reset_index().astype(int).values.tolist())

    # Reporting audit, on all rows
    source = vehicles["municipio"].map({MEDELLIN: "medellin", BOGOTA: "bogota"}).fillna("resto")
    monthly = (vehicles.assign(fuente=source).groupby(["m", "fuente"])
               .agg(n=("con_muertos", "size"), k=("con_muertos", "sum")).unstack("fuente", fill_value=0)
               .reindex(range(len(months)), fill_value=0))
    series = {f: {"n": monthly[("n", f)].astype(int).tolist(), "k": monthly[("k", f)].astype(int).tolist()}
              for f in ["medellin", "bogota", "resto"]}
    # Bulk load of Medellin spread in silver: rows moved into each month, and the published month
    moved = vehicles[(vehicles["municipio"] == MEDELLIN) & (vehicles["fecha_imputada"] == 1)]
    series["medellin_reubicados"] = moved.groupby("m").size().reindex(range(len(months)), fill_value=0).astype(int).tolist()
    bulk = None
    if len(moved):
        published = moved["periodo_original"].mode().iloc[0]
        kept = int(((vehicles["municipio"] == MEDELLIN) & (vehicles["periodo"] == published) & (vehicles["fecha_imputada"] == 0)).sum())
        bulk = {"periodo": published, "publicados": kept + len(moved), "conservados": kept, "reubicados": len(moved),
                "desde": moved["periodo"].min(), "hasta": moved["periodo"].max()}

    municipality_month = config.read_parquet(config.GOLD_MUNICIPIO_MES)
    top = vehicles["municipio"].value_counts().index[:TOP_MUNICIPALITIES].tolist()
    mm = municipality_month[municipality_month["municipio"].isin(top)].copy()
    mm["estado"] = NORMAL
    mm.loc[mm["alerta_caida"] == 1, "estado"] = DROP
    mm.loc[mm["alerta_carga_masiva"] == 1, "estado"] = BULK
    mm["m"] = mm["periodo"].map(month_index)
    full = range(len(months))
    status = mm.pivot(index="municipio", columns="m", values="estado").reindex(index=top, columns=full, fill_value=NORMAL)
    records = mm.pivot(index="municipio", columns="m", values="registros").reindex(index=top, columns=full, fill_value=0)
    reference = mm.groupby("municipio")["mediana_referencia"].first().reindex(top)

    # Edit made to the raw copy itself (scripts/redistribuir_carga_masiva.py), if any
    raw_edit = None
    if MANIFEST.exists():
        raw_edit = json.loads(MANIFEST.read_text(encoding="utf-8")).get("edicion_local")

    identical, age_offset = None, None
    if RAW_CSV.exists():
        raw = pd.read_csv(RAW_CSV, dtype=str)
        identical = int(raw.duplicated().sum())
        year = raw["FECHA_ACCIDENTE"].str[-4:].astype(int)
        offset = (pd.to_numeric(raw["EDAD_VEHICULO"], errors="coerce")
                  - (year - pd.to_numeric(raw["MODELO_VEHICULO"], errors="coerce")))
        age_offset = {str(y): float(v) for y, v in offset.groupby(year).median().items()}

    data = {
        "meta": {
            "fuente": "Ministerio de Transporte, RUNT. Vehículos involucrados en un accidente de tránsito, Ley 2251 de 2022 (datos.gov.co)",
            "generado": date.today().isoformat(),
            "filas": len(vehicles),
            "filas_limpias": len(clean),
            "filas_anomalas": int(vehicles["cobertura_anomala"].sum()),
            "filas_imputadas": int(vehicles["fecha_imputada"].sum()),
            "carga_masiva_medellin": bulk,
            "edicion_fuente": raw_edit,
            "filas_sin_edad": int(vehicles["edad"].isna().sum()),
            "filas_identicas": identical,
            "desfase_edad_fuente": age_offset,
            "municipios": int(vehicles["municipio"].nunique()),
            "municipios_evaluados": int(municipality_month.loc[municipality_month["municipio_evaluable"] == 1, "municipio"].nunique()),
            "departamentos": len(depts),
        },
        "dic": {
            "meses": months,
            "departamentos": depts,
            "tipos": types,
            "clases": [type_class.get(t, "otro") for t in types],
            "edades": [b[2] for b in AGE_BANDS],
        },
        "cubo": cube,
        "ciudades": {"nombres": cities, "departamento": city_dept, "cubo": city_cube},
        "fuentes": series,
        "cobertura": {"municipios": top, "estado": status.astype(int).values.tolist(),
                      "registros": records.astype(int).values.tolist(),
                      "referencia": [float(x) if pd.notna(x) else 0.0 for x in reference]},
        "modelo": model_section(),
    }
    OUT.write_text("/* Generado por scripts/exportar_tablero_runt.py desde la capa gold. No editar. */\n"
                   "window.DATOS_RUNT = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    print(f"dashboard: {len(vehicles)} vehicles ({len(clean)} outside anomalous months), {len(cube)} cube cells, "
          f"{len(months)} months, model section {'included' if data['modelo'] else 'skipped'} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
