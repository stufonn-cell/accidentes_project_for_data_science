"""Writes dashboard/data/datos.js, the offline copy of the dashboard data.

    python scripts/exportar_tablero_runt.py

The dashboard asks the API for its data (GET /tablero). This copy is the
fallback for opening dashboard/index.html straight from disk or with
python -m http.server, without the API. It computes the same document as
the pipeline stage src/tablero.py, from DATA_DIR (local folder or S3).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import tablero  # noqa: E402

OUT = ROOT / "dashboard" / "data" / "datos.js"


def main():
    data = tablero.build()
    OUT.write_text("/* Generado por scripts/exportar_tablero_runt.py desde la capa gold. No editar. */\n"
                   "window.DATOS_RUNT = " + tablero.to_json(data) + ";\n", encoding="utf-8")
    print(f"dashboard: {data['meta']['filas']} vehicles, {len(data['cubo'])} cube cells, "
          f"model section {'included' if data['modelo'] else 'skipped'} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
