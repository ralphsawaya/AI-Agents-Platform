"""Build the trading_agents zip file for upload to the platform."""

import os
import zipfile
from pathlib import Path

SOURCE_DIR = Path(__file__).parent
OUTPUT = Path(__file__).parent / "trading_agents.zip"

SKIP_NAMES = {"build_zip.py", "trading_agents.zip", "__pycache__", ".DS_Store"}


def build():
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
            for f in files:
                if f in SKIP_NAMES or f.endswith(".pyc"):
                    continue
                full_path = Path(root) / f
                arcname = "trading_agents/" + str(full_path.relative_to(SOURCE_DIR))
                zf.write(full_path, arcname)

    print(f"Created {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    print("Contents:")
    with zipfile.ZipFile(OUTPUT) as zf:
        for name in sorted(zf.namelist()):
            print(f"  {name}")


if __name__ == "__main__":
    build()
