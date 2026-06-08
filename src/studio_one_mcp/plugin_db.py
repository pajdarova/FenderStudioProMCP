"""Reads Studio One's DataStore.db to enumerate installed plugins."""
from __future__ import annotations

import platform
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Plugin:
    cid: str       # class ID GUID used in macro XML
    vendor: str
    name: str      # plugin name (from _subFolder)
    category: str  # AudioSynth, AudioEffect, MusicEffect, etc.


class PluginNotFoundError(Exception):
    pass


def _datastore_paths() -> list[Path]:
    system = platform.system()
    candidates: list[Path] = []
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "PreSonus"
        for ver in ("Studio One 7", "Studio One 6", "Studio One 5"):
            candidates.append(base / ver / "DataStore.db")
    elif system == "Windows":
        import os
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        for ver in ("Studio One 7", "Studio One 6", "Studio One 5"):
            candidates.append(base / "PreSonus" / ver / "DataStore.db")
    return candidates


def _find_datastore() -> Path | None:
    for p in _datastore_paths():
        if p.exists():
            return p
    return None


def list_plugins(category: str | None = None) -> list[Plugin]:
    """Return all plugins installed in Studio One (those with at least one preset)."""
    path = _find_datastore()
    if path is None:
        return []
    query = """
        SELECT DISTINCT _classID, _vendor, _subFolder, _category
        FROM PresetDescriptor
        WHERE _classID IS NOT NULL AND _classID != ''
          AND _subFolder IS NOT NULL AND _subFolder != ''
    """
    params: list[str] = []
    if category:
        query += " AND _category = ?"
        params.append(category)
    query += " ORDER BY _vendor, _subFolder"
    plugins: list[Plugin] = []
    try:
        with sqlite3.connect(str(path)) as conn:
            for row in conn.execute(query, params):
                plugins.append(
                    Plugin(
                        cid=row[0],
                        vendor=row[1] or "",
                        name=row[2] or "",
                        category=row[3] or "",
                    )
                )
    except sqlite3.Error:
        pass
    return plugins


def find_plugin(name: str) -> Plugin:
    """Find a plugin by name (case-insensitive, partial match).

    Raises PluginNotFoundError if not found.
    """
    plugins = list_plugins()
    name_lower = name.lower().strip()
    for p in plugins:
        if p.name.lower() == name_lower:
            return p
    for p in plugins:
        if name_lower in p.name.lower():
            return p
    known = sorted({p.name for p in plugins if p.name})
    raise PluginNotFoundError(
        f"Plugin {name!r} not found in Studio One preset database. "
        f"Known: {', '.join(known[:20])}"
        + (f" (+{len(known) - 20} more)" if len(known) > 20 else "")
    )
