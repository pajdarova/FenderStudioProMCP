"""Platform-aware keystroke sender for Studio One OS-level automation."""

from __future__ import annotations

import asyncio
import json
import os
import platform
from pathlib import Path
from typing import Any

_DEFAULT_KEYMAP = Path(__file__).parent / "keymap.json"

# AppleScript key codes for keys that can't be used with `keystroke`
_AS_KEY_CODES: dict[str, int] = {
    "return": 36,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "escape": 53,
    "backspace": 51,
    "delete": 51,
    "home": 115,
    "end": 119,
    "pageup": 116,
    "pagedown": 121,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "f1": 122,
    "f2": 120,
    "f3": 99,
    "f4": 118,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f8": 100,
    "f9": 101,
    "f10": 109,
    "f11": 103,
    "f12": 111,
}

_AS_MODIFIERS: dict[str, str] = {
    "cmd": "command down",
    "command": "command down",
    "shift": "shift down",
    "alt": "option down",
    "opt": "option down",
    "option": "option down",
    "ctrl": "control down",
    "control": "control down",
}


class KeystrokeError(Exception):
    pass


def _keymap_path() -> Path:
    override = os.environ.get("STUDIO_ONE_MCP_KEYMAP")
    return Path(override) if override else _DEFAULT_KEYMAP


def load_keymap() -> dict[str, Any]:
    path = _keymap_path()
    try:
        with path.open() as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except FileNotFoundError:
        raise KeystrokeError(f"Keymap not found: {path}. Set STUDIO_ONE_MCP_KEYMAP to override.")
    except json.JSONDecodeError as exc:
        raise KeystrokeError(f"Invalid keymap JSON at {path}: {exc}") from exc


def _platform_key() -> str:
    system = platform.system()
    if system == "Darwin":
        return "mac"
    if system == "Windows":
        return "windows"
    return "linux"


def _split_combo(combo: str) -> tuple[list[str], str]:
    """Split 'cmd+shift+a' into (['cmd', 'shift'], 'a')."""
    parts = combo.lower().split("+")
    return parts[:-1], parts[-1]


def _combo_to_applescript(combo: str) -> str:
    mods, key = _split_combo(combo)
    mod_parts = [_AS_MODIFIERS[m] for m in mods if m in _AS_MODIFIERS]
    mod_clause = ("{" + ", ".join(mod_parts) + "}") if mod_parts else ""

    if key in _AS_KEY_CODES:
        code = _AS_KEY_CODES[key]
        return f"key code {code}" + (f" using {mod_clause}" if mod_clause else "")
    if mod_clause:
        return f'keystroke "{key}" using {mod_clause}'
    return f'keystroke "{key}"'


def _build_applescript(app_name: str, keys: list[str], delay_ms: int, dialog: dict[str, Any] | None) -> str:
    lines: list[str] = [
        f'tell application "{app_name}" to activate',
        "delay 0.1",
        'tell application "System Events"',
    ]
    for combo in keys:
        lines.append(f"    {_combo_to_applescript(combo)}")
    if delay_ms:
        lines.append(f"    delay {delay_ms / 1000:.3f}")
    if dialog:
        if not delay_ms:
            lines.append("    delay 0.4")
        for confirm_key in dialog.get("confirm", []):
            lines.append(f"    {_combo_to_applescript(confirm_key)}")
    lines.append("end tell")
    return "\n".join(lines)


async def _run_subprocess(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return proc.returncode or 0, stderr.decode().strip()


async def _send_mac(app_name: str, action: dict[str, Any]) -> None:
    keys: list[str] = action["keys"]
    delay_ms: int = action.get("delay_ms", 0)
    dialog: dict[str, Any] | None = action.get("dialog")

    script = _build_applescript(app_name, keys, delay_ms, dialog)
    code, err = await _run_subprocess("osascript", "-e", script)
    if code != 0:
        raise KeystrokeError(f"osascript failed: {err}")


async def _send_linux(app_name: str, action: dict[str, Any]) -> None:
    keys: list[str] = action["keys"]
    delay_ms: int = action.get("delay_ms", 0)
    dialog: dict[str, Any] | None = action.get("dialog")

    # Bring window to focus
    code, _ = await _run_subprocess(
        "xdotool", "search", "--name", app_name, "windowactivate", "--sync"
    )
    if code != 0:
        raise KeystrokeError(f"xdotool: could not find window '{app_name}'. Is Studio One running?")

    await asyncio.sleep(0.1)

    for combo in keys:
        mods, key = _split_combo(combo)
        xdotool_combo = "+".join(mods + [key])
        await _run_subprocess("xdotool", "key", xdotool_combo)

    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)

    if dialog:
        if not delay_ms:
            await asyncio.sleep(0.4)
        for confirm_key in dialog.get("confirm", []):
            await _run_subprocess("xdotool", "key", confirm_key)


async def _send_windows(_app_name: str, _action: dict[str, Any]) -> None:
    raise KeystrokeError(
        "Windows keystroke automation is not yet implemented. "
        "Contributions welcome — see src/studio_one_mcp/keystrokes.py."
    )


async def send_action(action_name: str) -> None:
    """Send the keystrokes for *action_name* to Studio One.

    Reads keymap.json (or STUDIO_ONE_MCP_KEYMAP override) each call so edits
    take effect without restarting the server.

    Raises
    ------
    KeystrokeError
        If the action is unknown, has no mapping for the current platform, or
        requires a custom shortcut that has not been configured.
    """
    keymap = load_keymap()
    plat = _platform_key()
    app_name: str = keymap.get("app_name", {}).get(plat, "Studio One")

    actions: dict[str, Any] = keymap.get("actions", {})
    if action_name not in actions:
        known = ", ".join(sorted(actions))
        raise KeystrokeError(f"Unknown action {action_name!r}. Known actions: {known}")

    plat_action: dict[str, Any] | None = actions[action_name].get(plat)
    if plat_action is None:
        raise KeystrokeError(
            f"No keystroke mapping for {action_name!r} on {plat}. "
            "Edit keymap.json to add one."
        )

    if plat_action.get("custom") and not plat_action.get("keys"):
        raise KeystrokeError(
            f"Action {action_name!r} has no keys configured. "
            "See docs/shortcut-setup.md to assign a custom shortcut."
        )

    if plat == "mac":
        await _send_mac(app_name, plat_action)
    elif plat == "linux":
        await _send_linux(app_name, plat_action)
    else:
        await _send_windows(app_name, plat_action)
