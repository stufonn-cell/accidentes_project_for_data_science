"""Bronze layer: batch ingestion of the raw CSV.

Stores the data exactly as it comes from the source. Only the año
column is added to partition the storage.
"""

import pandas as pd

from src import config


def extract_year(date_text):
    """The source mixes ISO dates and day/month/year. Take the year from the text."""
    if "T" in date_text:
        return int(date_text[:4])
    return int(date_text[-4:])


def main():
    df = pd.read_csv(config.RAW_CSV, dtype=str)
    df["año"] = df["FECHA"].map(extract_year)

    config.prepare(config.BRONZE)
    df.to_parquet(config.BRONZE, index=False, partition_cols=["año"])
    print(f"bronze: {len(df)} rows written to {config.BRONZE}")


if __name__ == "__main__":
    main()
