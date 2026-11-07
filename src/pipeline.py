"""Runs the full pipeline: bronze, silver, gold and models."""

from src import bronze, gold, models, silver


def main():
    bronze.main()
    silver.main()
    gold.main()
    models.main()


if __name__ == "__main__":
    main()
