"""Models: predict whether an accident leaves victims, injured or dead.

Trains with accidents from 2010 to 2019 and evaluates with 2020 to
2022, a temporal split that mimics real use: predicting the future with
the past. Compares a logistic regression against a gradient boosting
and stores metrics, predictions and models in the gold layer.
"""

import io
import json

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, precision_score, recall_score,
                             roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder

from src import config

SPLIT_YEAR = 2020
CATEGORICAL = ["dia_semana", "franja", "clase_accidente", "causa", "barrio", "area"]
NUMERIC = ["hora", "mes"]
TARGET = "con_victimas"


def build_models():
    logistic = Pipeline([
        ("encode", ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ], remainder="passthrough")),
        ("classify", LogisticRegression(max_iter=2000)),
    ])
    boosting = Pipeline([
        ("encode", ColumnTransformer([
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
             CATEGORICAL),
        ], remainder="passthrough")),
        ("classify", HistGradientBoostingClassifier(random_state=42)),
    ])
    return {"regresion_logistica": logistic, "gradient_boosting": boosting}


def evaluate(y_true, proba):
    pred = (proba >= 0.5).astype(int)
    return {
        "roc_auc": round(roc_auc_score(y_true, proba), 4),
        "average_precision": round(average_precision_score(y_true, proba), 4),
        "brier": round(brier_score_loss(y_true, proba), 4),
        "precision": round(precision_score(y_true, pred), 4),
        "recall": round(recall_score(y_true, pred), 4),
        "matriz_confusion": confusion_matrix(y_true, pred).tolist(),
    }


def metrics_table(results):
    """One row per model with its metrics, the flat version of metricas.json."""
    rows = []
    for name, metrics in results["modelos"].items():
        (tn, fp), (fn, tp) = metrics["matriz_confusion"]
        rows.append({
            "modelo": name,
            "es_mejor": int(name == results["mejor_modelo"]),
            "roc_auc": metrics["roc_auc"],
            "average_precision": metrics["average_precision"],
            "brier": metrics["brier"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "verdaderos_negativos": tn,
            "falsos_positivos": fp,
            "falsos_negativos": fn,
            "verdaderos_positivos": tp,
            "filas_entrenamiento": results["particion"]["filas_entrenamiento"],
            "filas_prueba": results["particion"]["filas_prueba"],
            "prevalencia_prueba": results["particion"]["prevalencia_prueba"],
        })
    return pd.DataFrame(rows)


def main():
    df = config.read_parquet(config.GOLD_SINIESTROS)
    df["anio"] = df["anio"].astype(int)

    train = df[df["anio"] < SPLIT_YEAR]
    test = df[df["anio"] >= SPLIT_YEAR]
    x_train = train[CATEGORICAL + NUMERIC]
    x_test = test[CATEGORICAL + NUMERIC]

    results = {
        "objetivo": TARGET,
        "particion": {
            "entrenamiento": f"2010 a {SPLIT_YEAR - 1}",
            "prueba": f"{SPLIT_YEAR} a 2022",
            "filas_entrenamiento": len(train),
            "filas_prueba": len(test),
            "prevalencia_entrenamiento": round(train[TARGET].mean(), 4),
            "prevalencia_prueba": round(test[TARGET].mean(), 4),
        },
        "modelos": {},
    }

    config.prepare(config.GOLD_MODELOS)
    probas = {}
    for name, model in build_models().items():
        model.fit(x_train, train[TARGET])
        proba = model.predict_proba(x_test)[:, 1]
        probas[name] = proba
        results["modelos"][name] = evaluate(test[TARGET], proba)
        buffer = io.BytesIO()
        joblib.dump(model, buffer)
        config.write_bytes(f"{config.GOLD_MODELOS}/{name}.joblib", buffer.getvalue())

    best = max(results["modelos"], key=lambda m: results["modelos"][m]["roc_auc"])
    results["mejor_modelo"] = best

    # Each table in its own folder so Athena, and through it Power BI, can read it
    predictions = test[["radicado", "fecha", "anio", "barrio", TARGET]].copy()
    predictions["probabilidad"] = probas[best]
    config.write_parquet(predictions, f"{config.GOLD_MODELOS}/predicciones/predicciones.parquet")
    config.write_parquet(metrics_table(results),
                         f"{config.GOLD_MODELOS}/metricas/metricas.parquet")

    config.write_text(f"{config.GOLD_MODELOS}/metricas.json",
                      json.dumps(results, ensure_ascii=False, indent=2))

    print(json.dumps(results["modelos"], indent=2))
    print(f"best model: {best}")


if __name__ == "__main__":
    main()
