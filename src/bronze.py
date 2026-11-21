"""Bronze layer: the raw RUNT CSV stored as parquet.

Keeps every column exactly as it comes from the source, as text, and
every row, including the 159 thousand identical rows: the source has no
accident id, so two identical rows can be two different vehicles (see
silver). Two columns are added: id_registro, a unique identifier for
every vehicle record taken from its position in the source file (RUNT-000001
is the first row), and anio, taken from FECHA_ACCIDENTE (MM/AAAA), to
partition the storage. id_registro identifies a vehicle record, not an
accident: the source has no day, time or address, so which vehicles were in
the same crash cannot be known.
"""

from src import config


def main():
    df = config.read_csv(config.RAW_CSV, dtype=str, keep_default_na=False)
    df.insert(0, "id_registro", [f"RUNT-{i:06d}" for i in range(1, len(df) + 1)])
    df["anio"] = df["FECHA_ACCIDENTE"].str.strip().str[-4:].astype(int)

    config.prepare(config.BRONZE)
    config.write_parquet(df, config.BRONZE, partition_cols=["anio"])
    print(f"bronze: {len(df)} rows written to {config.BRONZE}")


if __name__ == "__main__":
    main()
