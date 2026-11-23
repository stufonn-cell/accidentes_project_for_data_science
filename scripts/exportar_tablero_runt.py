"""Writes dashboard/data/datos.js, the offline copy of the dashboard data.

    python scripts/exportar_tablero_runt.py

The dashboard asks the API for its data (GET /tablero). This copy is the
fallback for opening dashboard/index.html straight from disk or with
python -m http.server, without the API. It computes the same document as
the pipeline stage src/tablero.py, from DATA_DIR (local folder or S3).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import tablero  # noqa: E402

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
    best_name = description.get("mejor_modelo")
    search = description.get("busqueda_hiperparametros", {})
    best_search = search.get(best_name, {})
    winner = {
        "modelo": best_name,
        "validacion_agrupada": description.get("validacion_agrupada", {}).get(best_name, {}),
        "prueba_2024": description.get("modelos", {}).get(best_name, {}),
        "umbral": description.get("umbral_decision"),
        "hiperparametros": best_search.get("mejores", {}),
        "combinaciones_evaluadas": best_search.get("combinaciones", 0),
        "filas_muestra_busqueda": search.get("filas_muestra", 0),
        "variables": description.get("variables", {}),
        "particion": description.get("particion", {}),
        "criterio_seleccion": description.get("criterio_seleccion", ""),
    }
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
        "ganador": winner,
        "importancia_variables": [
            {"variable": r["variable"], "caida_pr_auc": float(r["caida_pr_auc"]),
             "desviacion": float(r["desviacion"])}
            for r in description.get("importancia_variables", [])
        ],
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
    data = tablero.build()
    OUT.write_text("/* Generado por scripts/exportar_tablero_runt.py desde la capa gold. No editar. */\n"
                   "window.DATOS_RUNT = " + tablero.to_json(data) + ";\n", encoding="utf-8")
    print(f"dashboard: {data['meta']['filas']} vehicles, {len(data['cubo'])} cube cells, "
          f"model section {'included' if data['modelo'] else 'skipped'} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
