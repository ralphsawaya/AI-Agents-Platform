#!/usr/bin/env python3
"""Package the trip_agents team into a zip for deployment."""

import os
import zipfile


def build():
    team_dir = os.path.dirname(os.path.abspath(__file__))
    zip_name = "trip_agents.zip"
    zip_path = os.path.join(team_dir, zip_name)

    excludes = {
        "__pycache__", ".git", ".env", "venv", ".venv",
        "node_modules", ".pytest_cache", ".mypy_cache",
        zip_name,
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(team_dir):
            dirs[:] = [d for d in dirs if d not in excludes]
            for fname in files:
                if fname.endswith((".pyc", ".pyo", ".zip")):
                    continue
                full_path = os.path.join(root, fname)
                arc_name = os.path.relpath(full_path, os.path.dirname(team_dir))
                zf.write(full_path, arc_name)

    print(f"Created {zip_path} ({os.path.getsize(zip_path):,} bytes)")


if __name__ == "__main__":
    build()
