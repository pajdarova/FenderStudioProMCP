"""Platform-aware keystroke sender for Studio One OS-level automation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import time
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    import ctypes as _ctypes_module

log = logging.getLogger(__name__)

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
    override = os.environ.get("STUDIO_PRO_MCP_KEYMAP")
    return Path(override) if override else _DEFAULT_KEYMAP


def load_keymap() -> dict[str, Any]:
    path = _keymap_path()
    try:
        with path.open() as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except FileNotFoundError as exc:
        raise KeystrokeError(
            f"Keymap not found: {path}. Set STUDIO_PRO_MCP_KEYMAP to override."
        ) from exc
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


# ---------------------------------------------------------------------------
# Windows keystroke automation (ctypes / SendInput, no third-party dependency)
# ---------------------------------------------------------------------------

# Virtual-key codes for the non-alphanumeric keys used by keymap.json.
# The OEM_* codes are positional: they address the physical key that Studio One
# stores in its shortcut table, independently of the active keyboard layout.
_VK_CODES: dict[str, int] = {
    "return": 0x0D, "enter": 0x0D, "tab": 0x09, "space": 0x20,
    "escape": 0x1B, "esc": 0x1B, "backspace": 0x08, "delete": 0x2E,
    "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "capslock": 0x14,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    ",": 0xBC, "-": 0xBD, ".": 0xBE, "=": 0xBB, ";": 0xBA,
    "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
    "+": 0xBB,  # same physical key as '='
}
for _fn in range(1, 25):
    _VK_CODES[f"f{_fn}"] = 0x6F + _fn  # F1 == 0x70

# Numeric keypad. These are layout-independent, which makes them a reliable
# fallback when an OEM key sits in a different place on a non-US keyboard.
for _num in range(10):
    _VK_CODES[f"num{_num}"] = 0x60 + _num
_VK_CODES.update({
    "nummultiply": 0x6A,
    "numplus": 0x6B,
    "numadd": 0x6B,
    "numminus": 0x6D,
    "numsubtract": 0x6D,
    "numdecimal": 0x6E,
    "numdivide": 0x6F,
})

_WIN_MODIFIERS: dict[str, int] = {
    "ctrl": 0x11, "control": 0x11,
    "shift": 0x10,
    "alt": 0x12, "opt": 0x12, "option": 0x12,
    "win": 0x5B, "cmd": 0x5B, "command": 0x5B,
}

# Window titles searched for, in order, unless overridden by the environment.
# Fender Studio Pro 8 titles its main window "Studio Pro - <project name>".
_WIN_TITLE_CANDIDATES = (
    "Fender Studio Pro",
    "Studio Pro",
    "Fender Studio",
    "Studio One",
)


def _vk_for_key(key: str) -> int:
    """Translate one keymap token into a Windows virtual-key code.

    Accepts a named key ("f3", "numplus", "delete"), a single character, or a
    raw code written as "vk:0xBB" for keys this table does not cover.
    """
    if key.startswith("vk:"):
        try:
            return int(key[3:], 0)
        except ValueError as exc:
            raise KeystrokeError(f"Malformed virtual-key token {key!r}.") from exc
    if key in _VK_CODES:
        return _VK_CODES[key]
    if len(key) == 1:
        if key.isdigit():
            return 0x30 + int(key)
        if key.isalpha():
            return ord(key.upper())
    raise KeystrokeError(f"No Windows virtual-key code known for {key!r}.")


class _Win32Bindings(Protocol):
    """Shape of the namespace ``_win32()`` returns.

    Purely a typing aid — ``ctypes``/``wintypes`` can't be imported at module
    level without breaking importability on macOS/Linux, so this describes
    the lazily-built object's shape without importing anything at runtime.
    """

    ctypes: ModuleType
    wintypes: ModuleType
    # ctypes.WinDLL only exists in typeshed's win32-conditional stubs, so
    # mypy running with a non-Windows --platform (e.g. CI on ubuntu-latest)
    # can't resolve it. Any keeps this Protocol checkable on every platform.
    user32: Any
    kernel32: Any
    INPUT: type[_ctypes_module.Structure]
    KEYBDINPUT: type[_ctypes_module.Structure]


def _win32() -> _Win32Bindings:
    """Lazily build the ctypes bindings and structures used for SendInput.

    Imported on demand so the module stays importable on macOS and Linux.
    """
    global _WIN32_CACHE
    cached = globals().get("_WIN32_CACHE")
    if cached is not None:
        return cast("_Win32Bindings", cached)

    import ctypes
    from ctypes import wintypes

    ulong_ptr = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    class MOUSEINPUT(ctypes.Structure):
        # Only needed so the union below gets its correct size.
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ulong_ptr),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    ns = type(
        "_Win32",
        (),
        {
            "ctypes": ctypes,
            "wintypes": wintypes,
            "user32": ctypes.WinDLL("user32", use_last_error=True),
            "kernel32": ctypes.WinDLL("kernel32", use_last_error=True),
            "INPUT": INPUT,
            "KEYBDINPUT": KEYBDINPUT,
        },
    )()
    globals()["_WIN32_CACHE"] = ns
    return cast("_Win32Bindings", ns)


def _find_window(titles: tuple[str, ...]) -> int:
    """Return the handle of the first visible window matching any title."""
    w = _win32()
    ctypes, wintypes, user32 = w.ctypes, w.wintypes, w.user32

    matches: list[tuple[int, int]] = []  # (candidate priority, hwnd)
    wanted = [t.lower() for t in titles]

    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()
        for priority, needle in enumerate(wanted):
            if needle in title:
                matches.append((priority, hwnd))
                break
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    if not matches:
        raise KeystrokeError(
            f"No window found matching any of {titles}. Is the DAW running? "
            "Set STUDIO_PRO_MCP_WINDOW_TITLE to override the search."
        )
    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def _focus_window(hwnd: int) -> None:
    """Bring a window to the foreground.

    Windows refuses SetForegroundWindow from a background process, so the
    calling thread is temporarily attached to the foreground thread first.
    """
    w = _win32()
    user32, kernel32 = w.user32, w.kernel32

    sw_restore = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, sw_restore)

    foreground = user32.GetForegroundWindow()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    )

    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)

    if user32.GetForegroundWindow() != hwnd:
        raise KeystrokeError(
            "Could not bring the DAW window to the foreground. "
            "Try running the MCP client without elevated privileges, or "
            "disable 'focus stealing' protection."
        )
    _ = target_thread  # kept for clarity; not needed further


def _send_key_events(vk_codes: list[int], key_up: bool) -> None:
    """Send a batch of key-down or key-up events via SendInput."""
    w = _win32()
    ctypes = w.ctypes
    input_type_keyboard = 1
    keyeventf_keyup = 0x0002

    count = len(vk_codes)
    array = (w.INPUT * count)()
    for i, vk in enumerate(vk_codes):
        array[i].type = input_type_keyboard
        array[i].ki = w.KEYBDINPUT(
            wVk=vk,
            wScan=0,
            dwFlags=keyeventf_keyup if key_up else 0,
            time=0,
            dwExtraInfo=0,
        )
    sent = w.user32.SendInput(count, array, ctypes.sizeof(w.INPUT))
    if sent != count:
        raise KeystrokeError(
            f"SendInput delivered {sent} of {count} events "
            f"(error {ctypes.get_last_error()})."
        )


def _send_unicode_text(text: str) -> None:
    """Type literal Unicode text via SendInput, bypassing virtual-key mapping.

    Unlike ``_send_key_events``, this doesn't go through a keyboard layout at
    all (``KEYEVENTF_UNICODE``), so punctuation in command names (``Save New
    Version...``) can't hit the OEM-key layout problem the shortcut path works
    around in ``keyscheme.py``.
    """
    w = _win32()
    ctypes = w.ctypes
    input_type_keyboard = 1
    keyeventf_unicode = 0x0004
    keyeventf_keyup = 0x0002

    for ch in text:
        code = ord(ch)
        for flags in (keyeventf_unicode, keyeventf_unicode | keyeventf_keyup):
            array = (w.INPUT * 1)()
            array[0].type = input_type_keyboard
            array[0].ki = w.KEYBDINPUT(
                wVk=0,
                wScan=code,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            )
            sent = w.user32.SendInput(1, array, ctypes.sizeof(w.INPUT))
            if sent != 1:
                raise KeystrokeError(
                    f"SendInput failed to type {ch!r} (error {ctypes.get_last_error()})."
                )


def _press_combo(combo: str) -> None:
    """Press and release one shortcut such as 'ctrl+shift+z'."""
    mods, key = _split_combo(combo)
    modifier_vks = [_WIN_MODIFIERS[m] for m in mods if m in _WIN_MODIFIERS]
    unknown = [m for m in mods if m not in _WIN_MODIFIERS]
    if unknown:
        raise KeystrokeError(f"Unknown modifier(s) {unknown} in {combo!r}.")

    key_vk = _vk_for_key(key)
    if modifier_vks:
        _send_key_events(modifier_vks, key_up=False)
    _send_key_events([key_vk], key_up=False)
    _send_key_events([key_vk], key_up=True)
    if modifier_vks:
        _send_key_events(list(reversed(modifier_vks)), key_up=True)


def _window_titles(app_name: str) -> tuple[str, ...]:
    override = os.environ.get("STUDIO_PRO_MCP_WINDOW_TITLE")
    if override:
        return (override,)
    titles = [app_name] if app_name else []
    titles += [t for t in _WIN_TITLE_CANDIDATES if t != app_name]
    return tuple(titles)


def _send_windows_blocking(app_name: str, action: dict[str, Any]) -> None:
    keys: list[str] = action["keys"]
    delay_ms: int = action.get("delay_ms", 0)
    dialog: dict[str, Any] | None = action.get("dialog")

    hwnd = _find_window(_window_titles(app_name))
    _focus_window(hwnd)
    time.sleep(0.1)

    for combo in keys:
        _press_combo(combo)

    if delay_ms:
        time.sleep(delay_ms / 1000)

    if dialog:
        if not delay_ms:
            time.sleep(0.4)
        for confirm_key in dialog.get("confirm", []):
            _press_combo(confirm_key)


async def _send_windows(app_name: str, action: dict[str, Any]) -> None:
    """Send the shortcut to the DAW window without blocking the event loop."""
    await asyncio.to_thread(_send_windows_blocking, app_name, action)


def _run_via_command_palette_blocking(
    app_name: str, text: str, *, confirm_dialog: bool
) -> None:
    hwnd = _find_window(_window_titles(app_name))
    _focus_window(hwnd)
    time.sleep(0.1)

    _press_combo("ctrl+k")
    time.sleep(0.2)
    _send_unicode_text(text)
    time.sleep(0.15)
    _press_combo("return")

    if confirm_dialog:
        time.sleep(0.4)
        _press_combo("return")


async def run_via_command_palette(text: str, *, confirm_dialog: bool = False) -> None:
    """Run *text* (a command or macro's readable name) via the DAW's Ctrl+K palette.

    Windows-only for now — macOS/Linux automation still goes through the
    AppleScript/xdotool shortcut paths.

    Unverified: whether Enter runs the top/only search result directly, and
    whether ``confirm_dialog`` commands (e.g. "Save New Version...") need the
    second Enter this sends for a name-confirmation dialog. Needs a real-DAW
    smoke test.
    """
    if platform.system() != "Windows":
        raise KeystrokeError("Command-palette dispatch is Windows-only for now.")

    keymap = load_keymap()
    app_name: str = keymap.get("app_name", {}).get("windows", "Studio One")
    await asyncio.to_thread(
        _run_via_command_palette_blocking, app_name, text, confirm_dialog=confirm_dialog
    )


def _resolve_keys(action_name: str, plat_action: dict[str, Any]) -> list[str]:
    """Return the shortcut to send for one platform-specific action entry.

    A ``"command"`` field (``"Category|Name"``) is looked up in the shortcut
    config generated from the user's own .keyscheme file, which is authoritative
    because users remap shortcuts. The ``"keys"`` field is the fallback for when
    no config exists or the command carries no shortcut in the DAW.
    """
    command = plat_action.get("command")
    if command:
        try:
            from studio_pro_mcp.keyscheme import load_shortcuts

            combos = load_shortcuts().get(command)
        except Exception as exc:  # a broken config must not break the fallback
            log.debug("Shortcut config unavailable (%s); using keymap.json", exc)
            combos = None
        if combos:
            return [combos[0]]

    keys = plat_action.get("keys")
    if keys:
        return list(keys)

    detail = f" (command {command!r} has no shortcut assigned in the DAW)" if command else ""
    raise KeystrokeError(
        f"Action {action_name!r} has no keys configured{detail}. "
        "Assign a shortcut in the DAW and regenerate the shortcut config, "
        "or add keys to keymap.json."
    )


async def send_command(category: str, name: str, *, confirm_dialog: bool = False) -> None:
    """Send the user's shortcut for one DAW command, e.g. ``("Edit", "Undo")``.

    ``confirm_dialog`` sends an extra Enter after a short delay, for commands
    that pop a confirmation dialog (e.g. a "name this version" prompt).
    """
    from studio_pro_mcp.keyscheme import load_shortcuts

    combos = load_shortcuts().get(f"{category}|{name}")
    if not combos:
        raise KeystrokeError(
            f"No shortcut known for command {category}|{name}. Generate the "
            "shortcut config with 'python -m studio_pro_mcp.keyscheme' and make "
            "sure the command has a shortcut assigned in the DAW."
        )

    keymap = load_keymap()
    plat = _platform_key()
    app_name: str = keymap.get("app_name", {}).get(plat, "Studio One")
    action: dict[str, Any] = {"keys": [combos[0]]}
    if confirm_dialog:
        action["dialog"] = {"confirm": ["return"]}

    if plat == "mac":
        await _send_mac(app_name, action)
    elif plat == "linux":
        await _send_linux(app_name, action)
    else:
        await _send_windows(app_name, action)


async def send_action(action_name: str) -> None:
    """Send the keystrokes for *action_name* to Studio One.

    Reads keymap.json (or STUDIO_PRO_MCP_KEYMAP override) each call so edits
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

    effective = dict(plat_action)
    effective["keys"] = _resolve_keys(action_name, plat_action)

    if plat == "mac":
        await _send_mac(app_name, effective)
    elif plat == "linux":
        await _send_linux(app_name, effective)
    else:
        await _send_windows(app_name, effective)
