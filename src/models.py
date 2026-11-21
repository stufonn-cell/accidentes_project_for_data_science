"""Models over gold/vehiculos: probability that an accident with victims had deaths.

Target con_muertos (1 = CON MUERTOS). Features: vehicle (tipo, marca
grouped, modelo, edad) and context of the record (mes, departamento,
autoridad de transito). The municipality is NOT a feature: the model is
meant for municipalities it did not see, and the grouped validation by
municipality would make a municipality id useless (always unseen in the
test fold). Rows in municipality-months with anomalous reporting
(cobertura_anomala) are left out of training.

Steps, all with fixed seeds:

1. Hyperparameter search (scikit-learn GridSearchCV, GroupKFold k=5 by
   municipality, scoring average precision) on a 120 thousand row sample
   of 2022-2024, for the logistic regression and the gradient boosting.
   The base document planned optuna; Glue only offers scikit-learn, so a
   small systematic grid is used instead.
2. Model selection: GroupKFold k=5 by municipality over all 2022-2024
   rows: prevalence, logistic regression (balanced class weights),
   HistGradientBoosting (balanced class weights) and random forest. The
   best mean PR-AUC wins.
3. Temporal check: train 2022-2023, test 2024. Each model is calibrated
   with isotonic regression (class weights distort the probabilities).
   2025-2026 is scored apart and flagged as coverage shifted.
4. Decision threshold from an explicit cost assumption: missing an
   accident with deaths costs COST_FN times a false alarm. With
   calibrated probabilities the cost minimizing threshold is
   1 / (1 + COST_FN).
5. Out-of-fold predictions by municipality (2022-2024) feed the expected
   lethality per municipality and the performance per cluster; the final
   model, trained on 2022-2024, scores 2025-2026.
6. Clustering of municipalities with >= 100 rows: k-means against
   agglomerative (ward) on standardized features, k by silhouette.

Only pandas, numpy, pyarrow, scikit-learn and joblib are used, so the
module runs in Glue. No optuna, shap or xgboost (deviation from the base
document): permutation importance stands in for SHAP.
"""

import io
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (adjusted_rand_score, average_precision_score, brier_score_loss,
                             confusion_matrix, roc_auc_score, silhouette_score)
from sklearn.model_selection import GridSearchCV, GroupKFold, learning_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from src import config

TARGET = "con_muertos"
CATEGORICAL = ["tipo_grupo", "marca_grupo", "departamento", "autoridad"]
NUMERIC = ["modelo", "edad", "mes"]
FEATURES = CATEGORICAL + NUMERIC
GROUP = "municipio"
SEED = 42
FOLDS = 5
SEARCH_ROWS = 120_000
MIN_CATEGORY_ROWS = 100
COST_FN = 10  # a missed accident with deaths costs 10 false alarms
THRESHOLD = round(1 / (1 + COST_FN), 4)
CLUSTER_FEATURES = ["prop_con_muertos", "edad_promedio", "prop_motos", "prop_carga",
                    "prop_autoridad_nacional", "log_registros"]
CLUSTER_K = range(2, 9)
VERSION_PREFIX = "runt"

HGB_GRID = {
    "clasificador__learning_rate": [0.05, 0.1],
    "clasificador__max_leaf_nodes": [15, 31, 63],
    "clasificador__l2_regularization": [0.0, 1.0],
}
LOGISTIC_GRID = {"clasificador__C": [0.01, 0.1, 1.0]}


# ------------------------------------------------------------------ models

def logistic():
    encode = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=MIN_CATEGORY_ROWS), CATEGORICAL),
        ("num", Pipeline([("imputar", SimpleImputer(strategy="median")), ("escalar", StandardScaler())]), NUMERIC),
    ])
    return Pipeline([("preparar", encode),
                     ("clasificador", LogisticRegression(class_weight="balanced", max_iter=2000, C=0.1))])


def ordinal_encoder():
    # Unknown or rare categories (e.g. the authority of an unseen municipality)
    # share one code; unknown ones become -1, which the trees treat as missing
    return ColumnTransformer([
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1,
                               min_frequency=MIN_CATEGORY_ROWS), CATEGORICAL),
        ("num", "passthrough", NUMERIC),
    ])


def gradient_boosting():
    categorical = [True] * len(CATEGORICAL) + [False] * len(NUMERIC)
    return Pipeline([("preparar", ordinal_encoder()),
                     ("clasificador", HistGradientBoostingClassifier(
                         categorical_features=categorical, class_weight="balanced", max_iter=300,
                         early_stopping=True, random_state=SEED))])


def random_forest():
    return Pipeline([("preparar", ordinal_encoder()),
                     ("imputar", SimpleImputer(strategy="median")),
                     ("clasificador", RandomForestClassifier(
                         n_estimators=60, max_depth=14, min_samples_leaf=20, max_samples=0.25,
                         class_weight="balanced_subsample", n_jobs=-1, random_state=SEED))])


def prevalence():
    return Pipeline([("clasificador", DummyClassifier(strategy="prior"))])


def calibrated(model):
    # Stratified 3 fold isotonic calibration; returns a Pipeline so callers
    # always get the same interface: predict_proba(DataFrame of FEATURES)
    return Pipeline([("calibrado", CalibratedClassifierCV(model, method="isotonic", cv=3))])


# ---------------------------------------------------------------- metrics

def evaluate(y, proba, threshold=THRESHOLD):
    y = np.asarray(y)
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "roc_auc": round(float(roc_auc_score(y, proba)), 4),
        "average_precision": round(float(average_precision_score(y, proba)), 4),
        "brier": round(float(brier_score_loss(y, proba)), 4),
        "precision": round(float(tp / (tp + fp)) if tp + fp else 0.0, 4),
        "recall": round(float(tp / (tp + fn)) if tp + fn else 0.0, 4),
        "verdaderos_negativos": int(tn), "falsos_positivos": int(fp),
        "falsos_negativos": int(fn), "verdaderos_positivos": int(tp),
        "tasa_alerta": round(float(pred.mean()), 4),
        "costo_esperado_por_registro": round(float((COST_FN * fn + fp) / len(y)), 4),
        "filas": int(len(y)),
        "prevalencia": round(float(y.mean()), 4),
    }


def reliability(y, proba, bins=10):
    """Calibration table: mean predicted vs observed rate by decile of the probability."""
    frame = pd.DataFrame({"y": np.asarray(y), "p": proba})
    frame["decil"] = pd.qcut(frame["p"].rank(method="first"), bins, labels=False)
    table = frame.groupby("decil").agg(prob_media=("p", "mean"), tasa_observada=("y", "mean"), filas=("y", "size"))
    return [{k: (round(float(v), 4) if k != "filas" else int(v)) for k, v in row.items()} | {"decil": int(i) + 1}
            for i, row in table.iterrows()]


# ------------------------------------------------------------------- data

def load():
    df = config.read_parquet(config.GOLD_VEHICULOS)
    df["anio"] = df["anio"].astype("int64")
    for col in CATEGORICAL + [GROUP]:
        df[col] = df[col].astype(object)
    for col in NUMERIC:
        df[col] = df[col].to_numpy(dtype="float64", na_value=np.nan)
    return df.reset_index(drop=True)


def cv_scores(model, x, y, groups):
    """Grouped CV: mean and sd of PR-AUC and ROC-AUC, train and validation."""
    rows = []
    for train, test in GroupKFold(n_splits=FOLDS).split(x, y, groups):
        model.fit(x.iloc[train], y.iloc[train])
        p_test = model.predict_proba(x.iloc[test])[:, 1]
        p_train = model.predict_proba(x.iloc[train])[:, 1]
        rows.append({"ap_validacion": average_precision_score(y.iloc[test], p_test),
                     "roc_validacion": roc_auc_score(y.iloc[test], p_test),
                     "ap_entrenamiento": average_precision_score(y.iloc[train], p_train),
                     "prevalencia_validacion": y.iloc[test].mean()})
    scores = pd.DataFrame(rows)
    return {
        "pr_auc_media": round(float(scores["ap_validacion"].mean()), 4),
        "pr_auc_desviacion": round(float(scores["ap_validacion"].std()), 4),
        "roc_auc_media": round(float(scores["roc_validacion"].mean()), 4),
        "roc_auc_desviacion": round(float(scores["roc_validacion"].std()), 4),
        "pr_auc_entrenamiento_media": round(float(scores["ap_entrenamiento"].mean()), 4),
        "pr_auc_por_pliegue": [round(float(v), 4) for v in scores["ap_validacion"]],
        "prevalencia_por_pliegue": [round(float(v), 4) for v in scores["prevalencia_validacion"]],
    }


def uncalibrated_proba(model, x):
    """Mean probability of the class weighted base models inside a calibrated pipeline."""
    inner = model.named_steps["calibrado"].calibrated_classifiers_
    return np.mean([c.estimator.predict_proba(x)[:, 1] for c in inner], axis=0)


def simple_rule(df):
    """Rule without a model: alert every cargo vehicle or national police record."""
    return ((df["tipo_grupo"].isin(["CAMION", "TRACTOCAMION", "VOLQUETA"])) | (df["autoridad"] == "DIRECCION DE TRANSITO Y TRANSPORTE")).astype(float).to_numpy()


# ------------------------------------------------------------- clustering

def cluster_municipalities():
    table = config.read_parquet(f"{config.GOLD_MUNICIPIO}/municipio.parquet")
    table = table[table["apto_agrupamiento"] == 1].copy()
    table["log_registros"] = np.log10(table["registros"])
    x = StandardScaler().fit_transform(table[CLUSTER_FEATURES])
    results = {"kmeans": {}, "jerarquico_ward": {}}
    labels = {}
    for k in CLUSTER_K:
        km = KMeans(n_clusters=k, n_init=20, random_state=SEED).fit_predict(x)
        ag = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(x)
        results["kmeans"][k] = round(float(silhouette_score(x, km)), 4)
        results["jerarquico_ward"][k] = round(float(silhouette_score(x, ag)), 4)
        labels[("kmeans", k)] = km
        labels[("jerarquico_ward", k)] = ag
    best_k = max(results["kmeans"], key=results["kmeans"].get)
    best_ag = max(results["jerarquico_ward"], key=results["jerarquico_ward"].get)
    table["grupo"] = (labels[("kmeans", best_k)] + 1).astype("int64")
    summary = {
        "municipios": int(len(table)),
        "filas_cubiertas": int(table["registros"].sum()),
        "variables": CLUSTER_FEATURES,
        "silueta": {alg: {str(k): v for k, v in s.items()} for alg, s in results.items()},
        "algoritmo_elegido": "kmeans",
        "k_elegido": int(best_k),
        "silueta_elegida": results["kmeans"][best_k],
        "mejor_k_jerarquico": int(best_ag),
        "silueta_mejor_jerarquico": results["jerarquico_ward"][best_ag],
        "rand_ajustado_kmeans_vs_jerarquico_mismo_k": round(float(adjusted_rand_score(
            labels[("kmeans", best_k)], labels[("jerarquico_ward", best_k)])), 4),
    }
    profile = table.groupby("grupo").agg(municipios=("municipio", "size"), registros=("registros", "sum"),
                                         **{c: (c, "mean") for c in CLUSTER_FEATURES[:-1]})
    summary["perfil_grupos"] = [{"grupo": int(g)} | {k: (round(float(v), 4) if isinstance(v, float) else int(v))
                                                    for k, v in row.items()} for g, row in profile.iterrows()]
    summary["ejemplos_por_grupo"] = {str(g): sub.nlargest(5, "registros")["municipio"].tolist()
                                     for g, sub in table.groupby("grupo")}
    columns = ["municipio", "municipio_nombre", "departamento", "grupo", "registros"] + CLUSTER_FEATURES
    return table[columns].reset_index(drop=True), summary


# -------------------------------------------------------------------- main

def save_model(model, name):
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    config.write_bytes(f"{config.GOLD_MODELOS}/{name}.joblib", buffer.getvalue())


def version():
    try:
        manifest = json.loads(config.read_bytes(config.RAW_MANIFEST))
        return f"{VERSION_PREFIX}-{manifest['fecha_descarga']}-{manifest['sha256'][:8]}"
    except (OSError, KeyError, ValueError):
        return f"{VERSION_PREFIX}-sin-manifiesto"


def main():
    df = load()
    clean = df["cobertura_anomala"] == 0
    base = df[df["anio"].between(2022, 2024) & clean].reset_index(drop=True)
    x_base, y_base, g_base = base[FEATURES], base[TARGET], base[GROUP]
    print(f"models: {len(base)} rows 2022-2024 without anomalous coverage, prevalence {y_base.mean():.4f}")

    # 1. hyperparameter search on a sample, grouped by municipality
    sample = base.sample(n=min(SEARCH_ROWS, len(base)), random_state=SEED)
    search = {}
    tuned = {}
    for name, factory, grid in [("regresion_logistica", logistic, LOGISTIC_GRID),
                                ("gradient_boosting", gradient_boosting, HGB_GRID)]:
        gs = GridSearchCV(factory(), grid, scoring="average_precision", cv=GroupKFold(n_splits=FOLDS), n_jobs=1)
        gs.fit(sample[FEATURES], sample[TARGET], groups=sample[GROUP])
        tuned[name] = gs.best_params_
        search[name] = {
            "espacio": {k.split("__")[1]: v for k, v in grid.items()},
            "mejores": {k.split("__")[1]: v for k, v in gs.best_params_.items()},
            "pr_auc_mejor": round(float(gs.best_score_), 4),
            "combinaciones": len(gs.cv_results_["params"]),
        }
        print(f"models: search {name} best {gs.best_params_} PR-AUC {gs.best_score_:.4f}")

    factories = {
        "prevalencia": prevalence,
        "regresion_logistica": lambda: logistic().set_params(**tuned["regresion_logistica"]),
        "gradient_boosting": lambda: gradient_boosting().set_params(**tuned["gradient_boosting"]),
        "bosque_aleatorio": random_forest,
    }

    # 2. model selection with grouped CV over all 2022-2024 rows
    grouped = {}
    for name, factory in factories.items():
        grouped[name] = cv_scores(factory(), x_base, y_base, g_base)
        print(f"models: grouped CV {name} PR-AUC {grouped[name]['pr_auc_media']} "
              f"+- {grouped[name]['pr_auc_desviacion']} ROC {grouped[name]['roc_auc_media']}")
    best = max((n for n in grouped if n != "prevalencia"), key=lambda n: grouped[n]["pr_auc_media"])

    # learning curve of the best model (bias vs variance) on the search sample
    sizes, train_scores, val_scores = learning_curve(
        factories[best](), sample[FEATURES], sample[TARGET], groups=sample[GROUP],
        cv=GroupKFold(n_splits=FOLDS), train_sizes=[0.1, 0.3, 1.0], scoring="average_precision")
    curve = [{"filas_entrenamiento": int(s), "pr_auc_entrenamiento": round(float(t.mean()), 4),
              "pr_auc_validacion": round(float(v.mean()), 4)}
             for s, t, v in zip(sizes, train_scores, val_scores)]

    # 3. temporal check: 2022-2023 -> 2024, calibrated models
    train = base[base["anio"] <= 2023]
    test = base[base["anio"] == 2024]
    temporal = {}
    temporal_models = {}
    probas = {}
    for name, factory in factories.items():
        model = factory() if name == "prevalencia" else calibrated(factory())
        model.fit(train[FEATURES], train[TARGET])
        proba = model.predict_proba(test[FEATURES])[:, 1]
        temporal[name] = evaluate(test[TARGET], proba)
        if name != "prevalencia":
            temporal[name]["brier_sin_calibrar"] = round(float(brier_score_loss(
                test[TARGET], uncalibrated_proba(model, test[FEATURES]))), 4)
        temporal_models[name] = model
        probas[name] = proba
        print(f"models: temporal 2024 {name} PR-AUC {temporal[name]['average_precision']} "
              f"ROC {temporal[name]['roc_auc']} recall {temporal[name]['recall']} "
              f"precision {temporal[name]['precision']} Brier {temporal[name]['brier']}")
    rule = evaluate(test[TARGET], simple_rule(test), threshold=0.5)
    calibration = reliability(test[TARGET], probas[best])

    # threshold check: cost of the theoretical threshold vs the best possible on 2024
    grid = np.round(np.arange(0.02, 0.5, 0.01), 2)
    costs = {float(t): evaluate(test[TARGET], probas[best], t)["costo_esperado_por_registro"] for t in grid}
    best_t = min(costs, key=costs.get)

    # permutation importance (stand in for SHAP) on a 2024 sample
    imp_sample = test.sample(n=min(30_000, len(test)), random_state=SEED)
    imp = permutation_importance(temporal_models[best], imp_sample[FEATURES], imp_sample[TARGET],
                                 scoring="average_precision", n_repeats=3, random_state=SEED)
    importance = sorted([{"variable": f, "caida_pr_auc": round(float(m), 4), "desviacion": round(float(s), 4)}
                         for f, m, s in zip(FEATURES, imp.importances_mean, imp.importances_std)],
                        key=lambda r: -r["caida_pr_auc"])

    # 5. out-of-fold predictions by municipality for 2022-2024 (all rows of the
    # test municipalities, trained without anomalous months), then final model
    period = df[df["anio"].between(2022, 2024)]
    oof = pd.Series(np.nan, index=period.index)
    for train_idx, test_idx in GroupKFold(n_splits=FOLDS).split(period, groups=period[GROUP]):
        fold_train = period.iloc[train_idx]
        fold_train = fold_train[fold_train["cobertura_anomala"] == 0]
        model = calibrated(factories[best]())
        model.fit(fold_train[FEATURES], fold_train[TARGET])
        oof.iloc[test_idx] = model.predict_proba(period.iloc[test_idx][FEATURES])[:, 1]

    final = calibrated(factories[best]())
    final.fit(x_base, y_base)
    recent = df[df["anio"] >= 2025]
    recent_proba = final.predict_proba(recent[FEATURES])[:, 1]
    shifted = {
        "todas_las_filas": evaluate(recent[TARGET], recent_proba),
        "sin_cobertura_anomala": evaluate(recent[TARGET][recent["cobertura_anomala"] == 0],
                                          recent_proba[(recent["cobertura_anomala"] == 0).to_numpy()]),
        "nota": "2025-2026 tiene cobertura cambiada (Medellin y Bogota casi dejan de reportar); "
                "no es comparable con 2024",
    }

    # 6. clusters and performance per cluster (out-of-fold, clean rows)
    groups_table, cluster_summary = cluster_municipalities()
    oof_frame = period.assign(probabilidad=oof)
    oof_clean = oof_frame[oof_frame["cobertura_anomala"] == 0]
    grouped_oof = evaluate(oof_clean[TARGET], oof_clean["probabilidad"].to_numpy())
    by_cluster = []
    with_group = oof_clean.merge(groups_table[["municipio", "grupo"]], on="municipio", how="left")
    with_group["grupo"] = with_group["grupo"].fillna(0).astype(int)  # 0 = fewer than 100 rows
    for g, sub in with_group.groupby("grupo"):
        if sub[TARGET].nunique() < 2:
            continue
        by_cluster.append({"grupo": int(g), "municipios": int(sub["municipio"].nunique())}
                          | evaluate(sub[TARGET], sub["probabilidad"].to_numpy()))

    # applied cases
    cases = pd.DataFrame([
        {"caso": "tractocamion en via nacional", "tipo_grupo": "TRACTOCAMION", "marca_grupo": "KENWORTH",
         "departamento": "CESAR", "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE", "modelo": 2012, "edad": 12, "mes": 12},
        {"caso": "moto nueva en Medellin", "tipo_grupo": "MOTOCICLETA", "marca_grupo": "AKT",
         "departamento": "ANTIOQUIA", "autoridad": "STRIA DE TTOYTTE MEDELLIN", "modelo": 2023, "edad": 1, "mes": 6},
        {"caso": "la misma moto en via nacional", "tipo_grupo": "MOTOCICLETA", "marca_grupo": "AKT",
         "departamento": "ANTIOQUIA", "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE", "modelo": 2023, "edad": 1, "mes": 6},
        {"caso": "automovil en Bogota", "tipo_grupo": "AUTOMOVIL", "marca_grupo": "CHEVROLET",
         "departamento": "BOGOTA D.C.", "autoridad": "SECRETARIA DISTRITAL DE MOVILIDAD DE BOGOTA", "modelo": 2015, "edad": 9, "mes": 3},
        {"caso": "bus intermunicipal en Boyaca", "tipo_grupo": "BUS", "marca_grupo": "CHEVROLET",
         "departamento": "BOYACA", "autoridad": "DIRECCION DE TRANSITO Y TRANSPORTE", "modelo": 2010, "edad": 14, "mes": 1},
    ])
    cases_x = cases[FEATURES].astype({c: "float64" for c in NUMERIC})
    cases["probabilidad"] = np.round(final.predict_proba(cases_x)[:, 1], 4)
    cases["alerta"] = (cases["probabilidad"] >= THRESHOLD).astype(int)

    # outputs
    config.prepare(config.GOLD_MODELOS)
    save_model(final, best)
    results = {
        "objetivo": TARGET,
        "version": version(),
        "particion": {
            "seleccion": f"GroupKFold k={FOLDS} por municipio sobre 2022-2024 sin meses con cobertura anomala",
            "entrenamiento": "2022-2023 sin meses con cobertura anomala",
            "prueba": "2024 sin meses con cobertura anomala",
            "aparte": "2025-2026, cobertura cambiada",
            "filas_entrenamiento": int(len(train)),
            "filas_prueba": int(len(test)),
            "prevalencia_entrenamiento": round(float(train[TARGET].mean()), 4),
            "prevalencia_prueba": round(float(test[TARGET].mean()), 4),
            "filas_modelo_final": int(len(base)),
            "filas_excluidas_cobertura_anomala_2022_2024": int((~clean & df["anio"].between(2022, 2024)).sum()),
        },
        "variables": {"categoricas": CATEGORICAL, "numericas": NUMERIC},
        "umbral_decision": THRESHOLD,
        "supuesto_costo": {"costo_falso_negativo": COST_FN, "costo_falso_positivo": 1,
                           "regla": "umbral = 1 / (1 + costo_falso_negativo), valido con probabilidades calibradas",
                           "umbral_optimo_observado_2024": best_t,
                           "costo_umbral_teorico_2024": temporal[best]["costo_esperado_por_registro"],
                           "costo_umbral_optimo_2024": costs[best_t],
                           "costo_sin_modelo_nunca_alertar": round(float(COST_FN * test[TARGET].mean()), 4),
                           "costo_alertar_todo": round(float(1 - test[TARGET].mean()), 4)},
        "mejor_modelo": best,
        "criterio_seleccion": "mayor PR-AUC media en validacion agrupada por municipio",
        "busqueda_hiperparametros": search | {"filas_muestra": int(len(sample)),
                                              "nota": "GridSearchCV de scikit-learn en lugar de optuna"},
        "validacion_agrupada": grouped,
        "curva_aprendizaje": curve,
        "modelos": temporal,
        "regla_simple_carga_o_autoridad_nacional": rule,
        "calibracion_prueba": calibration,
        "importancia_variables": importance,
        "validacion_agrupada_fuera_de_pliegue_mejor": grouped_oof,
        "cobertura_cambiada_2025_2026": shifted,
        "agrupamiento": cluster_summary,
        "desempeno_por_grupo": by_cluster,
        "casos": cases.to_dict(orient="records"),
    }
    config.write_text(f"{config.GOLD_MODELOS}/metricas.json", json.dumps(results, ensure_ascii=False, indent=2))

    rows = []
    for name, m in temporal.items():
        rows.append({"modelo": name, "evaluacion": "temporal_2024", "es_mejor": int(name == best)} | m
                    | {"pr_auc_cv_agrupada": grouped[name]["pr_auc_media"],
                       "roc_auc_cv_agrupada": grouped[name]["roc_auc_media"]})
    rows.append({"modelo": best, "evaluacion": "cobertura_cambiada_2025_2026", "es_mejor": 1} | shifted["todas_las_filas"])
    for c in by_cluster:
        rows.append({"modelo": best, "evaluacion": f"grupo_{c['grupo']}", "es_mejor": 1}
                    | {k: v for k, v in c.items() if k not in ("grupo", "municipios")})
    metrics = pd.DataFrame(rows)
    metrics["filas_entrenamiento"] = len(train)
    metrics["filas_prueba"] = metrics.pop("filas")
    metrics["prevalencia_prueba"] = metrics.pop("prevalencia")
    config.write_parquet(metrics, f"{config.GOLD_MODELOS}/metricas/metricas.parquet")

    keep = ["municipio", "departamento", "anio", "mes", "periodo", "tipo_grupo", "marca_grupo", "autoridad",
            "edad", "cobertura_anomala", TARGET]
    predictions = pd.concat([
        oof_frame[keep + ["probabilidad"]].assign(origen="fuera_de_pliegue_2022_2024"),
        recent[keep].assign(probabilidad=recent_proba, origen="modelo_final_2025_2026"),
    ], ignore_index=True)
    predictions["mes"] = predictions["mes"].astype("int64")
    predictions["probabilidad"] = predictions["probabilidad"].round(5)
    predictions["alerta"] = (predictions["probabilidad"] >= THRESHOLD).astype("int64")
    config.write_parquet(predictions, f"{config.GOLD_MODELOS}/predicciones/predicciones.parquet")

    config.write_parquet(groups_table, f"{config.GOLD_MODELOS}/grupos/grupos.parquet")

    lethality = (predictions[predictions["origen"] == "fuera_de_pliegue_2022_2024"]
                 .groupby(["municipio", "departamento"], as_index=False)
                 .agg(registros=(TARGET, "size"), con_muertos=(TARGET, "sum"),
                      observada=(TARGET, "mean"), esperada=("probabilidad", "mean")))
    lethality["diferencia"] = lethality["observada"] - lethality["esperada"]
    lethality["razon"] = lethality["observada"] / lethality["esperada"]
    lethality = lethality.merge(groups_table[["municipio", "grupo"]], on="municipio", how="left")
    lethality["grupo"] = lethality["grupo"].fillna(0).astype("int64")
    for col in ["observada", "esperada", "diferencia", "razon"]:
        lethality[col] = lethality[col].round(4)
    config.write_parquet(lethality.sort_values("registros", ascending=False),
                         f"{config.GOLD_MODELOS}/letalidad/letalidad.parquet")

    print(f"models: best {best}, threshold {THRESHOLD}, clusters k={cluster_summary['k_elegido']} "
          f"silhouette {cluster_summary['silueta_elegida']}, outputs in {config.GOLD_MODELOS}")


if __name__ == "__main__":
    main()
