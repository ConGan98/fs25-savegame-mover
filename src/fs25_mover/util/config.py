"""Persistent app config — remembers the FS25 root folder across launches.

Stored as JSON at `%APPDATA%/fs25-savegame-mover/config.json`. Falls back to
`~/.fs25-savegame-mover/config.json` on non-Windows systems.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "fs25-savegame-mover"
    return Path.home() / ".fs25-savegame-mover"


def _config_path() -> Path:
    return _config_dir() / "config.json"


@dataclass
class AppConfig:
    fs25_root: str | None = None
    last_output_dir: str | None = None

    @classmethod
    def load(cls) -> "AppConfig":
        p = _config_path()
        if not p.is_file():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(
            fs25_root=data.get("fs25_root"),
            last_output_dir=data.get("last_output_dir"),
        )

    def save(self) -> None:
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        _config_path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
