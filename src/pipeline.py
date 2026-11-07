"""Corre el pipeline completo: bronze, silver, gold y modelos."""

from src import bronze, gold, modelos, silver


def main():
    bronze.main()
    silver.main()
    gold.main()
    modelos.main()


if __name__ == "__main__":
    main()
