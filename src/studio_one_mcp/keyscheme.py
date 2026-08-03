"""Read a Fender Studio Pro / Studio One ``.keyscheme`` file and turn it into a
shortcut configuration that :mod:`studio_one_mcp.keystrokes` can consume.

The ``.keyscheme`` file is plain XML written by the DAW whenever the user
exports (or edits) a keyboard-shortcut scheme::

    <Commands name="Studio App">
        <Command category="Edit" name="Undo">
            <Key name="Ctrl+Z"/>
        </Command>
        ...
    </Commands>

Because users remap shortcuts freely, hard-coding them in ``keymap.json`` is
fragile. Generating the map from the user's own scheme removes the guesswork.

Command line
------------
::

    python -m studio_one_mcp.keyscheme                     # auto-discover + write
    python -m studio_one_mcp.keyscheme scheme.keyscheme -o shortcuts.json
    python -m studio_one_mcp.keyscheme --list Zoom         # inspect matches
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "KeySchemeError",
    "default_config_path",
    "discover_keyscheme",
    "load_shortcuts",
    "parse_keyscheme",
    "translate_combo",
]


class KeySchemeError(Exception):
    """Raised when a keyscheme file cannot be read or understood."""


# ---------------------------------------------------------------------------
# Token translation: DAW spelling -> keystrokes.py token
# ---------------------------------------------------------------------------

_MODIFIERS = {"ctrl": "ctrl", "shift": "shift", "alt": "alt"}

# Keys that address a physical position independent of keyboard layout.
_SAFE_KEYS: dict[str, str] = {
    "del": "delete",
    "backspace": "backspace",
    "ins": "insert",
    "return": "return",
    "enter": "return",
    "esc": "escape",
    "space": "space",
    "tab": "tab",
    "home": "home",
    "end": "end",
    "page up": "pageup",
    "page down": "pagedown",
    "left arrow": "left",
    "right arrow": "right",
    "up arrow": "up",
    "down arrow": "down",
    "caps lock": "capslock",
    "numpad+": "numplus",
    "numpad-": "numminus",
    "numpad*": "nummultiply",
    "numpad/": "numdivide",
    "numpad.": "numdecimal",
}
for _digit in range(10):
    _SAFE_KEYS[f"numpad{_digit}"] = f"num{_digit}"
for _fn in range(1, 13):
    _SAFE_KEYS[f"f{_fn}"] = f"f{_fn}"

# Punctuation reached through OEM virtual-key codes. These follow the physical
# layout of a US keyboard, so on other layouts they may land elsewhere. They are
# still emitted, only ranked below layout-independent alternatives.
_OEM_KEYS: dict[str, str] = {
    ",": ",",
    "-": "-",
    ".": ".",
    "/": "/",
    "=": "=",
    "+": "=",  # same physical key as '='
    ";": ";",
    "'": "'",
    "`": "`",
    "[": "[",
    "]": "]",
    "\\": "\\",
}

# Shifted punctuation: the scheme writes the shifted glyph without listing Shift.
_SHIFTED_KEYS: dict[str, str] = {
    "{": "[",
    "}": "]",
    ":": ";",
    '"': "'",
    "<": ",",
    ">": ".",
    "?": "/",
    "~": "`",
    "|": "\\",
    "_": "-",
}


def _split_modifiers(combo: str) -> tuple[list[str], str]:
    """Peel modifiers off the front; whatever remains is the key.

    Splitting naively on '+' breaks on shortcuts such as ``Ctrl++`` or
    ``Ctrl+NumPad+``, where the key itself is a plus sign.
    """
    rest = combo.strip()
    mods: list[str] = []
    while True:
        head, sep, tail = rest.partition("+")
        if not sep:
            break
        token = head.strip().lower()
        if token not in _MODIFIERS:
            break
        mods.append(_MODIFIERS[token])
        rest = tail
    return mods, rest.strip()


def translate_combo(combo: str) -> tuple[str | None, int, str | None]:
    """Translate one DAW shortcut into a keystrokes token string.

    Returns ``(token_string, penalty, problem)``. ``token_string`` is ``None``
    when the shortcut cannot be represented; ``penalty`` ranks layout-dependent
    variants below layout-independent ones.
    """
    mods, key = _split_modifiers(combo)
    if not key:
        return None, 0, f"empty key in {combo!r}"

    lowered = key.lower()

    if lowered in _SAFE_KEYS:
        return "+".join([*mods, _SAFE_KEYS[lowered]]), 0, None

    if len(key) == 1 and key.isalnum():
        return "+".join([*mods, lowered]), 0, None

    if lowered in _SHIFTED_KEYS:
        if "shift" not in mods:
            mods = [*mods, "shift"]
        return "+".join([*mods, _SHIFTED_KEYS[lowered]]), 2, None

    if lowered in _OEM_KEYS:
        return "+".join([*mods, _OEM_KEYS[lowered]]), 1, None

    return None, 0, f"unsupported key {key!r} in {combo!r}"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_keyscheme(path: str | Path) -> dict[str, Any]:
    """Parse a ``.keyscheme`` file into a serialisable shortcut map.

    Shortcuts are ordered best-first: layout-independent variants come before
    ones that depend on the physical keyboard layout.
    """
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise KeySchemeError(f"{path} is not valid XML: {exc}") from exc
    except OSError as exc:
        raise KeySchemeError(f"Cannot read {path}: {exc}") from exc

    if root.tag != "Commands":
        raise KeySchemeError(f"{path}: expected a <Commands> root, found <{root.tag}>.")

    shortcuts: dict[str, list[str]] = {}
    problems: list[str] = []
    total = 0

    for command in root.findall("Command"):
        category = command.get("category") or ""
        name = command.get("name") or ""
        if not name:
            continue
        total += 1

        ranked: list[tuple[int, int, str]] = []
        for order, key_el in enumerate(command.findall("Key")):
            raw = key_el.get("name")
            if not raw:
                continue
            token, penalty, problem = translate_combo(raw)
            if token is None:
                if problem:
                    problems.append(f"{category}|{name}: {problem}")
                continue
            ranked.append((penalty, order, token))

        if ranked:
            ranked.sort()
            seen: list[str] = []
            for _, _, token in ranked:
                if token not in seen:
                    seen.append(token)
            shortcuts[f"{category}|{name}"] = seen

    return {
        "source": str(path),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command_count": total,
        "shortcuts": shortcuts,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# Discovery and loading
# ---------------------------------------------------------------------------

def discover_keyscheme() -> Path | None:
    """Look for a ``.keyscheme`` file in the DAW's user-data folders."""
    from studio_one_mcp.plugin_db import _prefs_dirs

    candidates: list[Path] = []
    for directory in _prefs_dirs():
        if directory.is_dir():
            candidates.extend(directory.rglob("*.keyscheme"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def default_config_path() -> Path:
    """Where the generated shortcut config is written and read from."""
    override = os.environ.get("STUDIO_ONE_MCP_SHORTCUTS")
    if override:
        return Path(override)
    return Path.home() / ".studio_one_mcp" / "shortcuts.json"


def load_shortcuts(path: str | Path | None = None) -> dict[str, list[str]]:
    """Load the generated shortcut map, or return an empty map if absent."""
    target = Path(path) if path else default_config_path()
    if not target.is_file():
        return {}
    try:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise KeySchemeError(f"Cannot read shortcut config {target}: {exc}") from exc
    result = data.get("shortcuts", {})
    if not isinstance(result, dict):
        raise KeySchemeError(f"{target}: 'shortcuts' must be an object.")
    return result


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m studio_one_mcp.keyscheme",
        description="Convert a Studio Pro .keyscheme file into shortcuts.json.",
    )
    parser.add_argument("keyscheme", nargs="?", help="Path to the .keyscheme file.")
    parser.add_argument("-o", "--output", help="Where to write the config.")
    parser.add_argument("--list", metavar="TEXT", help="Print matching commands and exit.")
    parser.add_argument("--verbose", action="store_true", help="Report untranslatable keys.")
    args = parser.parse_args(argv)

    source = Path(args.keyscheme) if args.keyscheme else discover_keyscheme()
    if source is None:
        print(
            "No .keyscheme file found. Export one from the DAW "
            "(Preferences -> Keyboard Shortcuts) and pass its path.",
            file=sys.stderr,
        )
        return 2

    try:
        data = parse_keyscheme(source)
    except KeySchemeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.list is not None:
        needle = args.list.lower()
        for command, combos in sorted(data["shortcuts"].items()):
            if needle in command.lower():
                print(f"{command:55} {', '.join(combos)}")
        return 0

    destination = Path(args.output) if args.output else default_config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)

    print(f"Source:    {source}")
    print(f"Written:   {destination}")
    print(f"Commands:  {data['command_count']} scanned, {len(data['shortcuts'])} with a shortcut")
    if data["problems"]:
        print(f"Skipped:   {len(data['problems'])} shortcut(s) could not be translated")
        if args.verbose:
            for problem in data["problems"]:
                print(f"   {problem}")
        else:
            print("           (re-run with --verbose to list them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
