"""Runs the full pipeline: raw check, bronze, silver, gold, models, dashboard data
and the synthetic volume table (gold/vehiculos_expandido).

The download itself is a separate step (python -m src.ingesta) because it
depends on the portal. Here the current raw copy is validated again and
the run stops if it fails, so bad data never reaches bronze.
"""

from src import bronze, config, expand, gold, ingesta, models, silver, tablero


def main():
    try:
        profile = ingesta.check_current(config.read_bytes(config.RAW_CSV))
    except ingesta.ValidationError as error:
        raise SystemExit(f"pipeline: stopped, the raw copy fails validation. {error}")
    print(f"raw: {profile['filas']} rows, {profile['meses']} months "
          f"({profile['mes_minimo']} to {profile['mes_maximo']}), validation passed")
    bronze.main()
    silver.main()
    gold.main()
    models.main()
    tablero.main()
    expand.main()


if __name__ == "__main__":
    main()
