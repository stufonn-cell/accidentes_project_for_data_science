"""Packs the src package into build/src.zip for the Glue jobs.

Usage: python infra/scripts/build_zip.py
"""

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
OUT = ROOT / "build" / "src.zip"


def main():
    OUT.parent.mkdir(exist_ok=True)
    files = sorted(SRC.glob("*.py"))
    if not (SRC / "__init__.py").exists():
        raise SystemExit("src/__init__.py is missing: Glue needs it to import src from the zip")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f"src/{path.name}")
    print(f"Wrote {OUT.relative_to(ROOT)} with {len(files)} files")


if __name__ == "__main__":
    main()
