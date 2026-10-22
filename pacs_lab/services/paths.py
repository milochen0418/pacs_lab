"""Where the lab keeps its own files (the starter downloads, patient counters)."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """PACS_LAB_DATA_DIR, else ~/.local/share/pacs_lab (a Docker volume in the App Store)."""
    folder = Path(os.environ.get("PACS_LAB_DATA_DIR") or Path.home() / ".local/share/pacs_lab")
    folder.mkdir(parents=True, exist_ok=True)
    return folder
