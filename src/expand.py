"""Synthetic expansion of the silver layer to about 5 million rows.

Used to prove that the architecture, the partitions and the parquet
format handle a large volume. Each real row is replicated by shifting
its month k months, with k centred on 0, and the date dependent columns
are recomputed. The desplazamiento_meses column tracks the origin: 0 is
the real data.

The expanded data is synthetic. It is not used in the EDA nor in the
model evaluation, which work only with the real data.
"""

import math

import pandas as pd

from src import config

TARGET_ROWS = 5_000_000
BATCH = 4


def shift(df, months):
    copy = df.copy()
    copy["fecha"] = copy["fecha"] + pd.DateOffset(months=months)
    copy["anio"] = copy["fecha"].dt.year
    copy["mes"] = copy["fecha"].dt.month
    copy["periodo"] = copy["fecha"].dt.strftime("%Y-%m")
    copy["desplazamiento_meses"] = months
    return copy


def main():
    df = config.read_parquet(config.SILVER).drop(columns="anio")

    copies = math.ceil(TARGET_ROWS / len(df))
    shifts = range(-(copies // 2), copies - copies // 2)

    config.prepare(config.EXPANDED)
    total = 0
    batch = []
    for months in shifts:
        batch.append(shift(df, months))
        if len(batch) == BATCH or months == shifts[-1]:
            chunk = pd.concat(batch, ignore_index=True)
            config.write_parquet(chunk, config.EXPANDED, partition_cols=["anio"])
            total += len(chunk)
            batch = []
            print(f"expanded: {total} rows so far")

    print(f"expanded: {copies} copies of {len(df)} rows, "
          f"{total} rows written to {config.EXPANDED}")


if __name__ == "__main__":
    main()
