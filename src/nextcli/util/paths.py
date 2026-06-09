# Path utilities for Windows-safe file operations.

from __future__ import annotations

import os
from pathlib import Path

from nextcli.config import Config


def project_root() -> Path:
    # the current working directory
    return Path(os.getcwd()).resolve()


def cache_dir() -> Path:
    return Config.load().cache_dir


def resolve_under_root(path: str | os.PathLike[str], root: Path | None = None) -> Path:
    # resolve a path and make sure it stays under the project root
    base = (root or project_root()).resolve()
    candidate = (base / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise PermissionError(f"path {candidate} escapes project root {base}") from exc
    return candidate
