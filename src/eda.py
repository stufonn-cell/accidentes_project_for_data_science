"""Analisis exploratorio sobre la capa gold.

Genera las figuras del informe en reports/figuras y escribe en consola
los numeros que respaldan las conclusiones de reports/eda.md.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src import config

FIGURAS = "reports/figuras"
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def guardar(fig, nombre):
    fig.tight_layout()
    fig.savefig(f"{FIGURAS}/{nombre}.png", dpi=120)
    plt.close(fig)


def serie_mensual(siniestros):
    por_mes = siniestros.groupby(pd.Grouper(key="fecha", freq="MS")).size()
    fig, ax = plt.subplots(figsize=(10, 4))
    por_mes.plot(ax=ax, color="steelblue")
    ax.set_title("Siniestros por mes en Envigado, 2010 a 2022")
    ax.set_xlabel("")
    ax.set_ylabel("Siniestros")
    guardar(fig, "01_serie_mensual")


def dia_y_hora(siniestros):
    tabla = siniestros.pivot_table(index="dia_semana", columns="hora",
                                   values="radicado", aggfunc="size", fill_value=0)
    tabla = tabla.reindex(DIAS)
    fig, ax = plt.subplots(figsize=(11, 4))
    sns.heatmap(tabla, cmap="YlOrRd", ax=ax)
    ax.set_title("Siniestros por dia de la semana y hora")
    ax.set_xlabel("Hora del dia")
    ax.set_ylabel("")
    guardar(fig, "02_dia_hora")


def barrios(siniestros):
    top = siniestros["barrio"].value_counts().head(12).sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    top.plot.barh(ax=ax, color="steelblue")
    ax.set_title("Barrios con mas siniestros")
    ax.set_xlabel("Siniestros")
    guardar(fig, "03_barrios")


def gravedad_por_año(siniestros):
    tabla = siniestros.pivot_table(index="año", columns="gravedad",
                                   values="radicado", aggfunc="size", fill_value=0)
    proporcion = tabla.div(tabla.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(9, 4))
    proporcion[["SOLO DAÑOS", "HERIDOS", "MUERTOS"]].plot.bar(
        stacked=True, ax=ax, color=["lightgray", "orange", "firebrick"])
    ax.set_title("Composicion de la gravedad por año")
    ax.set_xlabel("")
    ax.set_ylabel("Proporcion")
    ax.legend(title="")
    guardar(fig, "04_gravedad_año")


def clases_y_causas(siniestros):
    fig, ejes = plt.subplots(1, 2, figsize=(12, 4))
    siniestros["clase_accidente"].value_counts().head(6).sort_values().plot.barh(
        ax=ejes[0], color="steelblue")
    ejes[0].set_title("Clases de accidente")
    siniestros["causa"].value_counts().head(8).sort_values().plot.barh(
        ax=ejes[1], color="steelblue")
    ejes[1].set_title("Causas mas frecuentes")
    guardar(fig, "05_clases_causas")


def victimas_por_franja(siniestros):
    tabla = siniestros.groupby("franja")["con_victimas"].mean()
    tabla = tabla.reindex(["madrugada", "manana", "tarde", "noche"])
    fig, ax = plt.subplots(figsize=(7, 4))
    tabla.plot.bar(ax=ax, color="orange")
    ax.set_title("Proporcion de siniestros con victimas por franja")
    ax.set_xlabel("")
    ax.set_ylabel("Proporcion con victimas")
    guardar(fig, "06_victimas_franja")


def resumen(siniestros):
    print(f"siniestros: {len(siniestros)}")
    print(f"rango de fechas: {siniestros['fecha'].min().date()} a {siniestros['fecha'].max().date()}")
    print("gravedad:")
    print(siniestros["gravedad"].value_counts().to_string())
    print(f"proporcion con victimas: {siniestros['con_victimas'].mean():.3f}")
    print("top 5 barrios:")
    print(siniestros["barrio"].value_counts().head(5).to_string())
    print("victimas por franja:")
    print(siniestros.groupby("franja")["con_victimas"].mean().round(3).to_string())
    print("victimas por clase:")
    print(siniestros.groupby("clase_accidente")["con_victimas"].mean().round(3).to_string())
    print(f"siniestros con coordenadas: {siniestros['lon'].notna().mean():.3f}")


def main():
    siniestros = pd.read_parquet(config.GOLD_SINIESTROS)
    siniestros["año"] = siniestros["año"].astype(int)

    serie_mensual(siniestros)
    dia_y_hora(siniestros)
    barrios(siniestros)
    gravedad_por_año(siniestros)
    clases_y_causas(siniestros)
    victimas_por_franja(siniestros)
    resumen(siniestros)
    print(f"figuras guardadas en {FIGURAS}")


if __name__ == "__main__":
    main()
