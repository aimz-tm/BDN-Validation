"""
Creates a clean release zip of the project.
Run from the project root:  python scripts/_make_release_zip.py
"""

import os
import zipfile
from pathlib import Path

SRC   = Path(__file__).resolve().parent.parent
OUT   = SRC.parent / "BDN-Validation-release.zip"

EXCLUDE_DIRS = {
    ".git", "__pycache__", ".claude", "uploads", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", "node_modules",
}

EXCLUDE_FILES = {
    Path("config") / ".env",
    Path("config") / "config.yaml.bak",
    Path("description.md"),
    Path("models_ml") / "isolation_forest.pkl",
    Path("data") / "ais_cache.py",
    Path("scripts") / "_make_release_zip.py",   # don't ship this script itself
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".pyd"}


def should_include(path: Path) -> bool:
    rel = path.relative_to(SRC)

    # Drop if any directory component is excluded
    for part in rel.parts[:-1]:
        if part in EXCLUDE_DIRS:
            return False

    # Drop specific files
    if rel in EXCLUDE_FILES:
        return False

    # Drop by extension
    if path.suffix in EXCLUDE_EXTENSIONS:
        return False

    return True


def main() -> None:
    included = [p for p in SRC.rglob("*") if p.is_file() and should_include(p)]
    included.sort()

    print(f"Source   : {SRC}")
    print(f"Output   : {OUT}")
    print(f"Including: {len(included)} files")

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in included:
            arc_name = "BDN-Validation/" + p.relative_to(SRC).as_posix()
            zf.write(p, arcname=arc_name)

    size_mb = OUT.stat().st_size / 1_048_576
    print(f"\nDone. {OUT.name} — {size_mb:.2f} MB")

    # Print what's included for a quick sanity check
    print("\nTop-level entries in zip:")
    with zipfile.ZipFile(OUT) as zf:
        tops = sorted({n.split("/")[1] for n in zf.namelist() if n.count("/") >= 1})
        for t in tops:
            print(f"  {t}/")


if __name__ == "__main__":
    main()
