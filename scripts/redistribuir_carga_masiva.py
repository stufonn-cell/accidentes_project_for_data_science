"""Removes the July 2024 bulk load of Medellin from the raw CSV and spreads it
over the months those reports most likely belong to.

    python scripts/redistribuir_carga_masiva.py

In July 2024 Medellin published 22.667 vehicles in a single month, almost ten
times its usual month (~2.500), and only 0.04 % of them in accidents with
deaths: late reports that were all uploaded with that date. The spike flattened
every other value of the dashboard.

The rule is the same one silver.redistribute_bulk_loads applies (and with the
same seed), only written into the raw copy:
- July 2024 keeps a typical month for Medellin: the 2022-2024 median, chosen
  at random;
- the excess is moved to Medellin's months from 2022-01 to 2024-06, in
  proportion to what each month reported, so seasonality is preserved, and
  never to a year earlier than the vehicle's model year minus one.
Only FECHA_ACCIDENTE changes; every other column, including the accident
severity, stays as published.

The untouched copy is saved in data/raw/historico/ and the manifest records
the edit (counts, months and both checksums). Running the script again does
nothing once the spike is gone. A new download with `python -m src.ingesta`
replaces the edited file with the portal's version.
"""

import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import silver  # noqa: E402

RAW = ROOT / "data" / "raw" / "vehiculos_siniestros_runt.csv"
MANIFEST = ROOT / "data" / "raw" / "manifiesto.json"
BACKUP_DIR = ROOT / "data" / "raw" / "historico"
MUNICIPALITY, DEPARTMENT, MONTH = "MEDELLIN", "ANTIOQUIA", "2024-07"


def main():
    raw_bytes = RAW.read_bytes()
    df = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    period = df["FECHA_ACCIDENTE"].str[-4:] + "-" + df["FECHA_ACCIDENTE"].str[:2]
    city = (df["MUNICIPIO_ACCIDENTE"].str.strip() == MUNICIPALITY) & (df["DEPARTAMENTO_ACCIDENTE"].str.strip() == DEPARTMENT)
    monthly = period[city].value_counts().sort_index()
    first, last = silver.REFERENCE_YEARS
    years = monthly.index.str[:4].astype(int)
    reference = monthly[(years >= first) & (years <= last)]
    keep = int(round(reference.median()))
    published = int(monthly.get(MONTH, 0))
    if published <= silver.BULK_RATIO * keep:
        print(f"{MUNICIPALITY} {MONTH}: {published} vehicles, no bulk load to spread (typical month ~{keep})")
        return

    rng = np.random.default_rng(silver.SEED)
    rows = df.index[city & (period == MONTH)].to_numpy()
    move = rng.permutation(rows)[keep:]
    past = monthly[(monthly.index >= f"{first}-01") & (monthly.index < MONTH)]
    past_year = past.index.str[:4].astype(int).to_numpy()
    model_year = pd.to_numeric(df.loc[move, "MODELO_VEHICULO"].str.strip(), errors="coerce")
    min_year = (model_year - 1).fillna(0).astype(int).to_numpy()
    new_period = pd.Series(MONTH, index=move)
    for year in np.unique(min_year):
        group = move[min_year == year]
        ok = past_year >= year
        if not ok.any():
            continue  # no compatible month: the vehicle stays in July
        counts = past.to_numpy()[ok]
        new_period[group] = rng.choice(past.index.to_numpy()[ok], size=len(group), p=counts / counts.sum())
    moved = new_period[new_period != MONTH]
    df.loc[moved.index, "FECHA_ACCIDENTE"] = moved.str[5:] + "/" + moved.str[:4]

    # Untouched copy first, then the edited file with the same quoting as the portal
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"vehiculos_siniestros_runt_{date.today().isoformat()}_antes_de_redistribuir.csv"
    if not backup.exists():
        shutil.copy2(RAW, backup)
    # Same format as the portal: every value in quotes except the empty ones
    quote = lambda v: f'"{v}"' if v != "" else ""
    lines = [",".join(quote(c) for c in df.columns)] + [",".join(quote(v) for v in row) for row in df.itertuples(index=False)]
    RAW.write_text("\n".join(lines) + "\n", encoding="utf-8")

    edited = RAW.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["sha256_portal"] = manifest.get("sha256_portal", hashlib.sha256(raw_bytes).hexdigest())
    manifest["sha256"] = hashlib.sha256(edited).hexdigest()
    manifest["edicion_local"] = {
        "fecha": date.today().isoformat(),
        "script": "scripts/redistribuir_carga_masiva.py",
        "descripcion": (f"Carga masiva de {MUNICIPALITY.title()} en {MONTH}: el mes conserva {keep} vehiculos "
                        f"(su mediana {first}-{last}) y los {len(moved)} restantes se reparten entre "
                        f"{past.index[0]} y {past.index[-1]} en proporcion a lo reportado cada mes. "
                        "Solo cambia FECHA_ACCIDENTE."),
        "municipio": f"{MUNICIPALITY} ({DEPARTMENT})",
        "periodo": MONTH,
        "publicados": published,
        "conservados": published - len(moved),
        "reubicados": int(len(moved)),
        "desde": past.index[0],
        "hasta": past.index[-1],
        "respaldo": str(backup.relative_to(ROOT)),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{MUNICIPALITY} {MONTH}: {published} -> {published - len(moved)} vehicles; "
          f"{len(moved)} moved to {past.index[0]}..{past.index[-1]}; original saved in {backup.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
