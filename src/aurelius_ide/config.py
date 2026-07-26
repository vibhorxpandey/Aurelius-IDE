"""Filesystem locations.

Standalone from ``aurelius-mcp``: the IDE resolves its own cache directory rather than
borrowing the MCP server's output directory, so the two can be installed independently.
Honours ``AURELIUS_IDE_CACHE_DIR``, then the XDG cache location, then a temp fallback.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def get_cache_dir() -> Path:
    """Directory for persisted analysis results. Created on demand."""
    override = os.environ.get("AURELIUS_IDE_CACHE_DIR")
    if override:
        path = Path(override)
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        path = Path(base) / "aurelius-ide"
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        path = Path(base) / "aurelius-ide"

    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "aurelius-ide"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
