"""Modelos: predicen si un siniestro deja victimas, heridos o muertos.

Entrena con los siniestros de 2010 a 2019 y evalua con los de 2020 a
2022, una particion temporal que imita el uso real: predecir el futuro
con el pasado. Compara una regresion logistica con un gradient boosting
y guarda metricas, predicciones e importancias en la capa gold.
"""

import json
import os

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

AÑO_CORTE = 2020
CATEGORICAS = ["dia_semana", "franja", "clase_accidente", "causa", "barrio", "area"]
NUMERICAS = ["hora", "mes"]
OBJETIVO = "con_victimas"


def construir_modelos():
    logistica = Pipeline([
        ("codificar", ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
        ], remainder="passthrough")),
        ("clasificar", LogisticRegression(max_iter=2000)),
    ])
    boosting = Pipeline([
        ("codificar", ColumnTransformer([
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
             CATEGORICAS),
        ], remainder="passthrough")),
        ("clasificar", HistGradientBoostingClassifier(random_state=42)),
    ])
    return {"regresion_logistica": logistica, "gradient_boosting": boosting}


def evaluar(y_real, proba):
    pred = (proba >= 0.5).astype(int)
    matriz = confusion_matrix(y_real, pred).tolist()
    return {
        "roc_auc": round(roc_auc_score(y_real, proba), 4),
        "average_precision": round(average_precision_score(y_real, proba), 4),
        "brier": round(brier_score_loss(y_real, proba), 4),
        "precision": round(precision_score(y_real, pred), 4),
        "recall": round(recall_score(y_real, pred), 4),
        "matriz_confusion": matriz,
    }


def main():
    df = pd.read_parquet(config.GOLD_SINIESTROS)
    df["año"] = df["año"].astype(int)

    entrena = df[df["año"] < AÑO_CORTE]
    prueba = df[df["año"] >= AÑO_CORTE]
    x_entrena = entrena[CATEGORICAS + NUMERICAS]
    x_prueba = prueba[CATEGORICAS + NUMERICAS]

    resultados = {
        "objetivo": OBJETIVO,
        "particion": {
            "entrenamiento": f"2010 a {AÑO_CORTE - 1}",
            "prueba": f"{AÑO_CORTE} a 2022",
            "filas_entrenamiento": len(entrena),
            "filas_prueba": len(prueba),
            "prevalencia_entrenamiento": round(entrena[OBJETIVO].mean(), 4),
            "prevalencia_prueba": round(prueba[OBJETIVO].mean(), 4),
        },
        "modelos": {},
    }

    config.preparar(config.GOLD_MODELOS)
    probas = {}
    for nombre, modelo in construir_modelos().items():
        modelo.fit(x_entrena, entrena[OBJETIVO])
        proba = modelo.predict_proba(x_prueba)[:, 1]
        probas[nombre] = proba
        resultados["modelos"][nombre] = evaluar(prueba[OBJETIVO], proba)
        if not config.ES_NUBE:
            joblib.dump(modelo, f"{config.GOLD_MODELOS}/{nombre}.joblib")

    mejor = max(resultados["modelos"], key=lambda m: resultados["modelos"][m]["roc_auc"])
    resultados["mejor_modelo"] = mejor

    predicciones = prueba[["radicado", "fecha", "año", "barrio", OBJETIVO]].copy()
    predicciones["probabilidad"] = probas[mejor]
    predicciones.to_parquet(f"{config.GOLD_MODELOS}/predicciones.parquet", index=False)

    with open(f"{config.GOLD_MODELOS}/metricas.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print(json.dumps(resultados["modelos"], indent=2))
    print(f"mejor modelo: {mejor}")


if __name__ == "__main__":
    main()
