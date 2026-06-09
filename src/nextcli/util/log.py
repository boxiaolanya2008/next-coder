# Simple logger that writes JSON lines to a file.
# Uses a file to avoid clashing with the Textual TUI.

from __future__ import annotations

import json
import time
from pathlib import Path

from nextcli.util.paths import cache_dir


_log_file: Path | None = None


def _log_path() -> Path:
    # get the log file path, create it once
    global _log_file
    if _log_file is None:
        _log_file = cache_dir() / "nextcli.log"
    return _log_file


def log_event(event: str, **fields: object) -> None:
    # append a json line to the log file, never raises
    try:
        record = {"ts": time.time(), "event": event, **fields}
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass
