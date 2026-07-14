"""Where rendered output files live.

Defaults to the user's Google Drive so finished videos + their manifest
sidecars sync off the laptop instead of piling up locally. Falls back to
the local ``output/`` folder when Drive isn't mounted (different machine or
Drive offline) so the pipeline never crashes. Override with the
``WBR_OUTPUT_DIR`` environment variable.
"""

import os
from pathlib import Path

_DRIVE_OUTPUT = Path(r"G:\My Drive\WorldBankRaces\output")


def output_dir(repo_root: Path) -> Path:
    override = os.environ.get("WBR_OUTPUT_DIR")
    if override:
        return Path(override)
    if _DRIVE_OUTPUT.parent.parent.exists():  # G:\My Drive present
        return _DRIVE_OUTPUT
    return repo_root / "output"
