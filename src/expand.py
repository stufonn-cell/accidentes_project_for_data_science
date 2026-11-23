"""Synthetic expansion of the gold vehicles table to at least one million rows.

Used to prove that the architecture, the partitions, the catalog and
Athena handle a larger volume. It writes a separate gold table,
gold/vehiculos_expandido/, partitioned by year like gold/vehiculos.

How a synthetic row is made: each real row of gold/vehiculos is copied
and its month shifted k months (k = -1, +1, -2, +2, ...), so every copy
keeps the joint distribution of the real data (type, brand, department,
authority, lethality) in a nearby month. The month dependent columns
(periodo, anio, mes, edad) are recomputed and id_registro gets the
shift as a suffix so it stays unique. Two columns tell real from
synthetic: es_sintetico (0 or 1) and desplazamiento_meses (0 is real).

The table holds the real rows too (es_sintetico = 0), so a count on it
gives the full volume. It is synthetic data: the model, the EDA and the
dashboard read only gold/vehiculos, never this table.

    python -m src.expand                  # at least 1,000,000 rows
    EXPAND_TARGET_ROWS=5000000 python -m src.expand
"""

import math
import os

import pandas as pd

from src import config

TARGET_ROWS = int(os.environ.get("EXPAND_TARGET_ROWS", "1000000"))


def shifts_for(copies):
    """Month shifts for the synthetic copies, closest to the real data first: -1, 1, -2, 2, ..."""
    out = []
    k = 1
    while len(out) < copies:
        out.append(-k)
        if len(out) < copies:
            out.append(k)
        k += 1
    return out


def shift(df, months):
    copy = df.copy()
    date = pd.to_datetime(copy["periodo"] + "-01") + pd.DateOffset(months=months)
    copy["periodo"] = date.dt.strftime("%Y-%m")
    copy["anio"] = date.dt.year
    copy["mes"] = date.dt.month.astype("int64")
    # Age at the (shifted) accident, floored at 0 as in silver
    copy["edad"] = (copy["anio"] - copy["modelo"]).clip(lower=0).astype("Float64")
    copy["id_registro"] = copy["id_registro"] + f"-S{months:+d}"
    copy["es_sintetico"] = 1
    copy["desplazamiento_meses"] = months
    return copy


def main():
    real = config.read_parquet(config.GOLD_VEHICULOS)
    real["anio"] = real["anio"].astype(int)
    real["es_sintetico"] = 0
    real["desplazamiento_meses"] = 0

    copies = max(math.ceil(TARGET_ROWS / len(real)) - 1, 0)
    config.prepare(config.GOLD_EXPANDIDO)
    # One write per copy keeps memory at about two copies of the table
    config.write_parquet(real, config.GOLD_EXPANDIDO, partition_cols=["anio"])
    total = len(real)
    for months in shifts_for(copies):
        config.write_parquet(shift(real, months), config.GOLD_EXPANDIDO, partition_cols=["anio"])
        total += len(real)
        print(f"expand: shift {months:+d} months, {total} rows so far")

    print(f"expand: {len(real)} real rows + {copies} synthetic copies = {total} rows "
          f"-> {config.GOLD_EXPANDIDO}")
    return total


if __name__ == "__main__":
    main()
