"""Filesystem locations."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
SEED_DIR = PACKAGE_DIR / "seed"


def data_dir() -> Path:
    override = os.environ.get("PS5CHEATER_HOME")
    if override:
        path = Path(override)
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "PS5 Cheater"
    else:
        path = Path.home() / ".ps5cheater"
    path.mkdir(parents=True, exist_ok=True)
    return path
