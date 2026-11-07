"""Exploratory analysis over the gold layer.

Generates the report figures in reports/figuras and prints the numbers
behind the conclusions of reports/eda.md. Titles and labels stay in
Spanish because the report is in Spanish.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src import config
from src.silver import DAYS

FIGURES = "reports/figuras"


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{FIGURES}/{name}.png", dpi=120)
    plt.close(fig)


def monthly_series(accidents):
    by_month = accidents.groupby(pd.Grouper(key="fecha", freq="MS")).size()
    fig, ax = plt.subplots(figsize=(10, 4))
    by_month.plot(ax=ax, color="steelblue")
    ax.set_title("Siniestros por mes en Envigado, 2010 a 2022")
    ax.set_xlabel("")
    ax.set_ylabel("Siniestros")
    save(fig, "01_serie_mensual")


def day_and_hour(accidents):
    table = accidents.pivot_table(index="dia_semana", columns="hora",
                                  values="radicado", aggfunc="size", fill_value=0)
    table = table.reindex(DAYS)
    fig, ax = plt.subplots(figsize=(11, 4))
    sns.heatmap(table, cmap="YlOrRd", ax=ax)
    ax.set_title("Siniestros por dia de la semana y hora")
    ax.set_xlabel("Hora del dia")
    ax.set_ylabel("")
    save(fig, "02_dia_hora")


def neighborhoods(accidents):
    top = accidents["barrio"].value_counts().head(12).sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    top.plot.barh(ax=ax, color="steelblue")
    ax.set_title("Barrios con mas siniestros")
    ax.set_xlabel("Siniestros")
    save(fig, "03_barrios")


def severity_by_year(accidents):
    table = accidents.pivot_table(index="año", columns="gravedad",
                                  values="radicado", aggfunc="size", fill_value=0)
    share = table.div(table.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(9, 4))
    share[["SOLO DAÑOS", "HERIDOS", "MUERTOS"]].plot.bar(
        stacked=True, ax=ax, color=["lightgray", "orange", "firebrick"])
    ax.set_title("Composicion de la gravedad por año")
    ax.set_xlabel("")
    ax.set_ylabel("Proporcion")
    ax.legend(title="")
    save(fig, "04_gravedad_año")


def classes_and_causes(accidents):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    accidents["clase_accidente"].value_counts().head(6).sort_values().plot.barh(
        ax=axes[0], color="steelblue")
    axes[0].set_title("Clases de accidente")
    accidents["causa"].value_counts().head(8).sort_values().plot.barh(
        ax=axes[1], color="steelblue")
    axes[1].set_title("Causas mas frecuentes")
    save(fig, "05_clases_causas")


def victims_by_time_slot(accidents):
    table = accidents.groupby("franja")["con_victimas"].mean()
    table = table.reindex(["madrugada", "manana", "tarde", "noche"])
    fig, ax = plt.subplots(figsize=(7, 4))
    table.plot.bar(ax=ax, color="orange")
    ax.set_title("Proporcion de siniestros con victimas por franja")
    ax.set_xlabel("")
    ax.set_ylabel("Proporcion con victimas")
    save(fig, "06_victimas_franja")


def summary(accidents):
    print(f"accidents: {len(accidents)}")
    print(f"date range: {accidents['fecha'].min().date()} to {accidents['fecha'].max().date()}")
    print("severity:")
    print(accidents["gravedad"].value_counts().to_string())
    print(f"share with victims: {accidents['con_victimas'].mean():.3f}")
    print("top 5 neighborhoods:")
    print(accidents["barrio"].value_counts().head(5).to_string())
    print("victims by time slot:")
    print(accidents.groupby("franja")["con_victimas"].mean().round(3).to_string())
    print("victims by class:")
    print(accidents.groupby("clase_accidente")["con_victimas"].mean().round(3).to_string())
    print(f"accidents with coordinates: {accidents['lon'].notna().mean():.3f}")


def main():
    accidents = pd.read_parquet(config.GOLD_SINIESTROS)
    accidents["año"] = accidents["año"].astype(int)

    monthly_series(accidents)
    day_and_hour(accidents)
    neighborhoods(accidents)
    severity_by_year(accidents)
    classes_and_causes(accidents)
    victims_by_time_slot(accidents)
    summary(accidents)
    print(f"figures saved to {FIGURES}")


if __name__ == "__main__":
    main()
