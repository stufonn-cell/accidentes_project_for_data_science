"""Packs the src package into build/src.zip for the Glue jobs.

Usage: python infra/scripts/build_zip.py
"""

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGES = ["src"]
OUT = ROOT / "build" / "src.zip"


def main():
    OUT.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for package in PACKAGES:
            folder = ROOT / package
            if not (folder / "__init__.py").exists():
                raise SystemExit(f"{package}/__init__.py is missing: Glue needs it to import {package} from the zip")
            for path in sorted(folder.glob("*.py")):
                zf.write(path, f"{package}/{path.name}")
                count += 1
    print(f"Wrote {OUT.relative_to(ROOT)} with {count} files")


if __name__ == "__main__":
    main()
