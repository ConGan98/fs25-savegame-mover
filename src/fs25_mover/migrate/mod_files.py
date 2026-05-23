"""Copy a chosen list of source mod files into the migrated savegame folder.

Runs AFTER `Savegame.write_to()` so source files overwrite anything the
target had with the same name (per user's "source wins" preference).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModFileMigrationResult:
    copied: list[str] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)
    error: str | None = None


def copy_mod_files(
    source_dir: Path | str,
    output_dir: Path | str,
    includes: list[str],
) -> ModFileMigrationResult:
    """Copy each filename in `includes` from `source_dir` into `output_dir`.

    Files in `includes` that don't exist in source are recorded in
    `skipped_missing` rather than erroring — the user may have ticked a
    known-safe filename that this particular save doesn't actually have.
    Any genuine I/O failure is reported in `error`.
    """
    result = ModFileMigrationResult()
    src = Path(source_dir)
    out = Path(output_dir)
    if not src.is_dir() or not out.is_dir():
        result.error = f"missing folder: src={src} exists={src.is_dir()}, out={out} exists={out.is_dir()}"
        return result
    for name in includes:
        src_file = src / name
        if not src_file.is_file():
            result.skipped_missing.append(name)
            continue
        try:
            shutil.copy2(src_file, out / name)
            result.copied.append(name)
        except OSError as exc:
            result.error = f"failed copying {name}: {exc}"
            return result
    return result
