"""Synthetic expansion of the silver layer to 5 million rows.

Used to prove that the architecture, the partitions and the parquet
format handle a large volume. Each real row is replicated by shifting
its date k months, with k between -48 and 48, and the date dependent
columns are recomputed. The desplazamiento_meses column tracks the
origin: 0 is the real data.

The expanded data is synthetic. It is not used in the EDA nor in the
model evaluation, which work only with the real data.
"""

import math

import pandas as pd

from src import config
from src.silver import DAYS

TARGET_ROWS = 5_000_000
BATCH = 10


def shift(df, months):
    copy = df.copy()
    copy["fecha_hora"] = copy["fecha_hora"] + pd.DateOffset(months=months)
    copy["fecha"] = copy["fecha_hora"].dt.normalize()
    copy["año"] = copy["fecha"].dt.year
    copy["mes"] = copy["fecha"].dt.month
    copy["dia_semana"] = copy["fecha"].dt.weekday.map(dict(enumerate(DAYS)))
    copy["desplazamiento_meses"] = months
    return copy


def main():
    df = config.read_parquet(config.SILVER)
    df = df.drop(columns="año")

    copies = math.ceil(TARGET_ROWS / len(df))
    shifts = range(-(copies // 2), copies - copies // 2)

    config.prepare(config.EXPANDED)
    total = 0
    batch = []
    for months in shifts:
        batch.append(shift(df, months))
        if len(batch) == BATCH or months == shifts[-1]:
            chunk = pd.concat(batch, ignore_index=True)
            config.write_parquet(chunk, config.EXPANDED, partition_cols=["año"])
            total += len(chunk)
            batch = []
            print(f"expanded: {total} rows so far")

    print(f"expanded: {copies} copies of {len(df)} rows, "
          f"{total} rows written to {config.EXPANDED}")


if __name__ == "__main__":
    main()
