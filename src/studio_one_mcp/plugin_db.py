"""Enumerates installed plugins from Studio One's settings files.

Primary source: Plugins-en.settings (all scanned plugins — AU, VST2, VST3, built-ins).
Secondary:      AUPlugins.settings (AU-only, used when primary is absent).
Fallback:       DataStore.db (SQLite, only plugins that have at least one preset).
"""
from __future__ import annotations

import platform
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


@dataclass
class Plugin:
    cid: str       # class ID GUID used in macro XML
    vendor: str
    name: str      # plugin display name
    category: str  # AudioSynth, AudioEffect, MusicEffect, etc.


class PluginNotFoundError(Exception):
    pass


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _prefs_dirs() -> list[Path]:
    """Return candidate PreSonus user-data directories in priority order."""
    system = platform.system()
    candidates: list[Path] = []
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "PreSonus"
        for ver in ("Studio One 7", "Studio One 6", "Studio One 5"):
            candidates.append(base / ver)
    elif system == "Windows":
        import os
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        for ver in ("Studio One 7", "Studio One 6", "Studio One 5"):
            candidates.append(base / "PreSonus" / ver)
    return candidates


def _find_settings(filename: str) -> Path | None:
    for d in _prefs_dirs():
        p = d / filename
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Plugins-en.settings parser
#
# PreSonus .settings XML looks like:
#
#   <Attributes>
#     <Attribute id="/path/to/Plugin.vst3" members="classID name vendor …">
#       <Attribute id="classID" value="{GUID}"/>
#       <Attribute id="name"    value="Plugin Name"/>
#       <Attribute id="vendor"  value="Vendor"/>
#       <Attribute id="category" value="AudioEffect"/>
#       …
#     </Attribute>
#     …
#   </Attributes>
#
# Some Studio One versions omit the outer wrapper and use flat key=value pairs
# inside an Attribute element; we handle both.
# ---------------------------------------------------------------------------

def _parse_plugins_en(path: Path) -> list[Plugin]:
    try:
        tree = ElementTree.parse(str(path))
    except ElementTree.ParseError:
        return []

    root = tree.getroot()
    plugins: list[Plugin] = []

    # Each top-level <Attribute> is one plugin entry (keyed by path/id)
    for entry in root.findall("Attribute"):
        child_map: dict[str, str] = {}
        for child in entry.findall("Attribute"):
            cid_attr = child.get("id", "")
            val = child.get("value", "")
            if cid_attr:
                child_map[cid_attr] = val

        cid = child_map.get("classID", "")
        name = child_map.get("name", "") or child_map.get("pluginName", "")
        vendor = child_map.get("vendor", "") or child_map.get("manufacturer", "")
        category = child_map.get("category", "") or child_map.get("subCategory", "")

        if not cid or not name:
            continue

        # Normalise category to the Studio One convention
        category = _normalise_category(category)
        plugins.append(Plugin(cid=cid, vendor=vendor, name=name, category=category))

    return plugins


# ---------------------------------------------------------------------------
# AUPlugins.settings parser  (AU-only fallback)
# ---------------------------------------------------------------------------

def _parse_au_plugins(path: Path) -> list[Plugin]:
    """Parse AUPlugins.settings — same XML structure as Plugins-en.settings."""
    return _parse_plugins_en(path)


# ---------------------------------------------------------------------------
# DataStore.db fallback (SQLite — only plugins that have presets)
# ---------------------------------------------------------------------------

def _datastore_paths() -> list[Path]:
    return [d / "DataStore.db" for d in _prefs_dirs()]


def _find_datastore() -> Path | None:
    for p in _datastore_paths():
        if p.exists():
            return p
    return None


def _parse_datastore() -> list[Plugin]:
    path = _find_datastore()
    if path is None:
        return []
    query = """
        SELECT DISTINCT _classID, _vendor, _subFolder, _category
        FROM PresetDescriptor
        WHERE _classID IS NOT NULL AND _classID != ''
          AND _subFolder IS NOT NULL AND _subFolder != ''
        ORDER BY _vendor, _subFolder
    """
    plugins: list[Plugin] = []
    try:
        with sqlite3.connect(str(path)) as conn:
            for row in conn.execute(query):
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


# ---------------------------------------------------------------------------
# Category normalisation
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    # VST3 sub-category strings → Studio One category names
    "instrument": "AudioSynth",
    "synth": "AudioSynth",
    "synthesizer": "AudioSynth",
    "generator": "AudioSynth",
    "fx": "AudioEffect",
    "audio fx": "AudioEffect",
    "audio effect": "AudioEffect",
    "dynamics": "AudioEffect",
    "eq": "AudioEffect",
    "equalizer": "AudioEffect",
    "filter": "AudioEffect",
    "reverb": "AudioEffect",
    "delay": "AudioEffect",
    "modulation": "AudioEffect",
    "pitch": "AudioEffect",
    "distortion": "AudioEffect",
    "mastering": "AudioEffect",
    "restoration": "AudioEffect",
    "analyzer": "AudioEffect",
    "spatial": "AudioEffect",
    "surround": "AudioEffect",
    "music effect": "MusicEffect",
    "midi": "MusicEffect",
    # Direct pass-through values already in Studio One form
    "audiosynth": "AudioSynth",
    "audioeffect": "AudioEffect",
    "musiceffect": "MusicEffect",
}

_GUID_RE = re.compile(r"^\{[0-9A-Fa-f\-]{36}\}$")


def _normalise_category(raw: str) -> str:
    if not raw:
        return ""
    lower = raw.lower().strip()
    # Try exact match first, then partial containment
    if lower in _CATEGORY_MAP:
        return _CATEGORY_MAP[lower]
    for key, val in _CATEGORY_MAP.items():
        if key in lower:
            return val
    # Return the raw value so callers still have it
    return raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_plugins(category: str | None = None) -> list[Plugin]:
    """Return plugins installed in Studio One.

    Reads Plugins-en.settings (comprehensive) → AUPlugins.settings → DataStore.db.
    """
    plugins: list[Plugin] = []

    plugins_en = _find_settings("Plugins-en.settings")
    if plugins_en:
        plugins = _parse_plugins_en(plugins_en)

    if not plugins:
        au_path = _find_settings("AUPlugins.settings")
        if au_path:
            plugins = _parse_au_plugins(au_path)

    if not plugins:
        plugins = _parse_datastore()

    if category:
        cat_lower = category.lower()
        plugins = [p for p in plugins if p.category.lower() == cat_lower]

    # De-duplicate by (cid, name) keeping first occurrence
    seen: set[tuple[str, str]] = set()
    deduped: list[Plugin] = []
    for p in plugins:
        key = (p.cid, p.name)
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    return sorted(deduped, key=lambda p: (p.vendor.lower(), p.name.lower()))


def find_plugin(name: str) -> Plugin:
    """Find a plugin by name (case-insensitive, partial match).

    Raises PluginNotFoundError if not found.
    """
    plugins = list_plugins()
    name_lower = name.lower().strip()
    # Exact match
    for p in plugins:
        if p.name.lower() == name_lower:
            return p
    # Partial match
    for p in plugins:
        if name_lower in p.name.lower():
            return p
    known = sorted({p.name for p in plugins if p.name})
    raise PluginNotFoundError(
        f"Plugin {name!r} not found in Studio One plugin database. "
        f"Known: {', '.join(known[:20])}"
        + (f" (+{len(known) - 20} more)" if len(known) > 20 else "")
    )
