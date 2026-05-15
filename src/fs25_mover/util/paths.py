"""Best-guess default paths on Windows."""
from __future__ import annotations

import os
from pathlib import Path


def default_savegames_dir() -> Path | None:
    """Documents\\My Games\\FarmingSimulator2025 if it exists, else None."""
    docs = os.environ.get("USERPROFILE") or str(Path.home())
    candidate = Path(docs) / "Documents" / "My Games" / "FarmingSimulator2025"
    return candidate if candidate.is_dir() else None
