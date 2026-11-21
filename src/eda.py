"""Exploratory analysis of the RUNT vehicles in accidents with victims.

Reads silver (one row per vehicle) and gold/municipio_mes, generates the
report figures in reports/figuras and prints the numbers behind
reports/eda.md: profile of the 9 source variables, coverage audit by
municipality and month, and class imbalance. Titles and labels stay in
Spanish because the report is in Spanish.
"""

import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from src import config

FIGURES = "reports/figuras"
RED = "firebrick"
BLUE = "steelblue"


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{FIGURES}/{name}.png", dpi=120)
    plt.close(fig)


def profile(df, raw):
    print("== profile of the 9 source variables ==")
    print(f"rows: {len(df)}, identical rows: {int(raw.duplicated().sum())}")
    for col in raw.columns:
        empty = int((raw[col].fillna("").str.strip() == "").sum())
        print(f"{col}: {raw[col].nunique()} distinct raw values, {empty} empty")
    print(f"brands after normalization: {df['marca'].nunique()}, kept in marca_grupo: "
          f"{df['marca_grupo'].nunique() - 1} (+ OTRAS with {int((df['marca_grupo'] == 'OTRAS').sum())} rows)")
    print(f"authorities after normalization: {df['autoridad'].nunique()}")
    print(f"municipality keys: {df['municipio'].nunique()}, names: {df['municipio_nombre'].nunique()}, "
          f"departments: {df['departamento'].nunique()}, months: {df['periodo'].nunique()}")
    print("vehicle type share:")
    print(df["tipo"].value_counts(normalize=True).head(8).round(4).to_string())
    print("vehicle class share and deaths:")
    print(df.groupby("clase_vehiculo")["con_muertos"].agg(["size", "mean"]).round(4).to_string())
    print(f"model year: {int(df['modelo'].min())} to {int(df['modelo'].max())}, "
          f"impossible: {int(df['modelo_invalido'].sum())}")
    print(f"edad at accident: median {df['edad'].median()}, mean {df['edad'].mean():.2f}; "
          f"source EDAD_VEHICULO median {df['edad_fuente'].median()}, mean {df['edad_fuente'].mean():.2f}")
    gap = (df["edad_fuente"] - df["edad"]).dropna()
    print(f"EDAD_VEHICULO - edad: median {gap.median()}, by year "
          f"{df.assign(g=df['edad_fuente'] - df['edad']).groupby('anio')['g'].median().to_dict()}")


def imbalance(df):
    print("== imbalance ==")
    deaths = int(df["con_muertos"].sum())
    print(f"con muertos: {deaths} of {len(df)} ({deaths / len(df):.4f})")
    by_muni = df.groupby("municipio")["con_muertos"].sum()
    print(f"municipalities with 0 deaths: {int((by_muni == 0).sum())}, with >= 10: {int((by_muni >= 10).sum())}")
    print("share with deaths by year:")
    print(df.groupby("anio")["con_muertos"].agg(["size", "mean"]).round(4).to_string())
    no_med = df[df["municipio"] != "MEDELLIN (ANTIOQUIA)"]
    print("share with deaths by year without Medellin:")
    print(no_med.groupby("anio")["con_muertos"].mean().round(4).to_string())
    print("share with deaths by authority type (1 = national police):")
    print(df.groupby("autoridad_nacional")["con_muertos"].agg(["size", "mean"]).round(4).to_string())
    print("share with deaths by type (top 10):")
    top = df["tipo"].value_counts().index[:10]
    print(df[df["tipo"].isin(top)].groupby("tipo")["con_muertos"].mean().sort_values().round(4).to_string())


def coverage(df, months):
    print("== coverage audit ==")
    big = df["municipio"].value_counts().head(5).index
    print("rows per year in the 5 largest municipalities:")
    print(df[df["municipio"].isin(big)].pivot_table(index="municipio", columns="anio", values="con_muertos",
                                                    aggfunc="size", fill_value=0).to_string())
    judged = months[months["municipio_evaluable"] == 1]
    print(f"municipalities judged (median 2022-2024 >= 5 rows a month): {judged['municipio'].nunique()}")
    print("alerts by year (municipality-months):")
    print(months.groupby("anio")[["alerta_caida", "alerta_carga_masiva", "alerta_cobertura"]].sum().to_string())
    print(f"rows in municipality-months with an alert: {int(df['cobertura_anomala'].sum())} "
          f"({df['cobertura_anomala'].mean():.4f})")
    worst = (judged.groupby("municipio")["alerta_caida"].sum().sort_values(ascending=False).head(8))
    print("municipalities with most drop months:")
    print(worst.to_string())
    bulk = months[months["alerta_carga_masiva"] == 1].sort_values("registros", ascending=False).head(5)
    print("largest bulk loads:")
    print(bulk[["municipio", "periodo", "registros", "mediana_referencia"]].to_string(index=False))
    print(f"municipalities with >= 100 rows: {(df['municipio'].value_counts() >= 100).sum()}, "
          f"share of rows: {df['municipio'].value_counts()[lambda s: s >= 100].sum() / len(df):.4f}")


def figures(df, months):
    os.makedirs(FIGURES, exist_ok=True)
    monthly = df.groupby("fecha").agg(registros=("con_muertos", "size"), prop=("con_muertos", "mean"))
    fig, ax = plt.subplots(figsize=(10, 4))
    monthly["registros"].plot(ax=ax, color=BLUE, label="Registros")
    ax.set_ylabel("Vehiculos registrados")
    ax2 = ax.twinx()
    (monthly["prop"] * 100).plot(ax=ax2, color=RED, label="% con muertos")
    ax2.set_ylabel("% con muertos")
    ax.set_title("Vehiculos en siniestros con victimas por mes, Colombia 2022-2026")
    ax.set_xlabel("")
    save(fig, "01_serie_mensual")

    top = df["municipio"].value_counts().head(20).index
    heat = (months[months["municipio"].isin(top)].pivot(index="municipio", columns="periodo", values="registros")
            .reindex(top))
    share = heat.div(heat.max(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(share.values, aspect="auto", cmap="viridis")
    ax.set_yticks(range(len(top)), top, fontsize=7)
    ticks = list(range(0, share.shape[1], 6))
    ax.set_xticks(ticks, [share.columns[i] for i in ticks], fontsize=7)
    ax.set_title("Cobertura: registros por mes / maximo del municipio (20 municipios con mas registros)")
    save(fig, "07_cobertura_municipio_mes")

    top_types = df["tipo"].value_counts().index[:10]
    rate = df[df["tipo"].isin(top_types)].groupby("tipo")["con_muertos"].mean().sort_values() * 100
    fig, ax = plt.subplots(figsize=(8, 5))
    rate.plot.barh(ax=ax, color=RED)
    ax.axvline(df["con_muertos"].mean() * 100, color="gray", linestyle="--")
    ax.set_title("% de registros con muertos por tipo de vehiculo")
    ax.set_xlabel("% con muertos")
    ax.set_ylabel("")
    save(fig, "08_muertos_por_tipo")

    by_age = df[df["edad"] <= 30].groupby("edad")["con_muertos"].mean() * 100
    fig, ax = plt.subplots(figsize=(8, 4))
    by_age.plot(ax=ax, color=RED, marker="o")
    ax.set_title("% con muertos por edad del vehiculo al momento del siniestro")
    ax.set_xlabel("Edad (años)")
    ax.set_ylabel("% con muertos")
    save(fig, "09_muertos_por_edad")


def main():
    raw = config.read_csv(config.RAW_CSV, dtype=str, keep_default_na=False)
    df = config.read_parquet(config.SILVER)
    df["anio"] = df["anio"].astype(int)
    months = config.read_parquet(f"{config.GOLD_MUNICIPIO_MES}/municipio_mes.parquet")
    profile(df, raw)
    imbalance(df)
    coverage(df, months)
    figures(df, months)
    print(f"figures saved to {FIGURES}")


if __name__ == "__main__":
    main()
