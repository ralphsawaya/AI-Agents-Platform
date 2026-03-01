"""Build the TeamAB agent zip file for upload to the platform."""

import os
import zipfile
from pathlib import Path

SOURCE_DIR = Path(__file__).parent / "team_ab"
OUTPUT = Path(__file__).parent / "team_ab.zip"


def build():
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                full_path = Path(root) / f
                arcname = "team_ab/" + str(full_path.relative_to(SOURCE_DIR))
                zf.write(full_path, arcname)

    print(f"Created {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    print("Contents:")
    with zipfile.ZipFile(OUTPUT) as zf:
        for name in sorted(zf.namelist()):
            print(f"  {name}")


if __name__ == "__main__":
    build()
