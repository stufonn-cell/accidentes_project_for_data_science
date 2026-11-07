"""Capa bronze: ingesta por lotes del CSV crudo.

Guarda los datos tal como llegan de la fuente, sin limpiarlos. Solo se
agrega la columna año para particionar el almacenamiento.
"""

import pandas as pd

from src import config


def extraer_año(fecha):
    """La fuente mezcla fechas ISO y dia/mes/año. El año se saca del texto."""
    if "T" in fecha:
        return int(fecha[:4])
    return int(fecha[-4:])


def main():
    df = pd.read_csv(config.RAW_CSV, dtype=str)
    df["año"] = df["FECHA"].map(extraer_año)

    config.preparar(config.BRONZE)
    df.to_parquet(config.BRONZE, index=False, partition_cols=["año"])
    print(f"bronze: {len(df)} filas escritas en {config.BRONZE}")


if __name__ == "__main__":
    main()
