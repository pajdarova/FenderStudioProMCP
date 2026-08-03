# Windows support

StudioOneMcp was written against macOS. This document covers the changes that
make it run on Windows, plus a tool that reads the DAW's own keyboard-shortcut
file so the keystroke path uses each user's actual shortcuts.

Applies to Fender Studio Pro 8 (the rebranded PreSonus Studio One) and to
Studio One 6/7.

## What was missing

| Module | Problem | Fix |
|---|---|---|
| `keystrokes.py` | `_send_windows()` raised `KeystrokeError` — no implementation existed | Keystroke delivery via `SendInput` (ctypes, no new dependency) |
| `midi_bridge.py` | Always called `open_virtual_port()`, which python-rtmidi's WinMM backend does not support | On Windows, attach to an existing loopback port instead |
| `plugin_db.py` | Only probed `Studio One 5/6/7` user-data folders | Added Fender Studio Pro folder names |

`keymap.json` already carried Windows shortcuts for all 24 actions, so only the
sender was missing.

## Install

```powershell
git clone https://github.com/tiwadara/StudioOneMcp
cd StudioOneMcp
py -m venv .venv
.\.venv\Scripts\pip install -e .
```

The README's install line (`./.venv/bin/pip`) is a POSIX path; on Windows use
`.\.venv\Scripts\pip`.

### Pin the MCP SDK

`mcp` 2.0 removed the low-level decorator API (`Server.list_tools()`,
`Server.call_tool()`) that `server.py` relies on, so a fresh install crashes at
startup with:

```
AttributeError: 'Server' object has no attribute 'list_tools'
```

Constrain the dependency in `pyproject.toml`:

```toml
dependencies = [
    "mcp>=1.0.0,<2",
    "python-rtmidi>=1.5.0",
    "anyio>=4.0.0",
    "click>=8.1.0",
]
```

Release 1.29.0 is the last of the 1.x line and supports Python 3.10 through 3.14.

### Register with an MCP client

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "studio-one": {
      "command": "C:\\path\\to\\StudioOneMcp\\.venv\\Scripts\\studio-one-mcp.exe"
    }
  }
}
```

Use the absolute path to the executable inside the virtual environment; a bare
command name will not be found.

## Keystroke automation

Keystrokes go through `SendInput`. Before sending, the DAW window is located
with `EnumWindows` and brought to the foreground. Windows blocks
`SetForegroundWindow` from background processes, so the calling thread is
temporarily attached to the foreground thread — the same technique other
automation tools use.

### Window title

Fender Studio Pro titles its main window `Studio Pro - <project name>`. These
titles are matched, in order, case-insensitively, as substrings:

```
Fender Studio Pro, Studio Pro, Fender Studio, Studio One
```

Override the search with an environment variable:

```powershell
$env:STUDIO_ONE_MCP_WINDOW_TITLE = "Studio Pro"
```

### Verify

With the DAW running and a song open:

```powershell
.\.venv\Scripts\python -c "import asyncio; from studio_one_mcp.keystrokes import send_action; asyncio.run(send_action('save'))"
```

The DAW should come forward and save.

## Shortcuts from the user's own key scheme

Hard-coding shortcuts in `keymap.json` is fragile: users remap freely, and the
defaults shipped in that file came from Studio One 7, where several no longer
match. `s` is Solo rather than Split, Split is `Alt+X`, and Toggle Loop is
`NumPad/` rather than `Ctrl+L`.

`keyscheme.py` reads the DAW's native `.keyscheme` file — plain XML, exported
from *Preferences → Keyboard Shortcuts* — and writes a `shortcuts.json` that
`keystrokes.py` consults first.

```powershell
.\.venv\Scripts\python -m studio_one_mcp.keyscheme
```

With no argument the file is auto-discovered under the DAW's user-data folders.
Otherwise pass a path:

```powershell
.\.venv\Scripts\python -m studio_one_mcp.keyscheme "C:\path\Studio_Pro.keyscheme"
```

Output goes to `%USERPROFILE%\.studio_one_mcp\shortcuts.json`, overridable with
`STUDIO_ONE_MCP_SHORTCUTS`. Regenerate after changing shortcuts in the DAW.

Inspect what was parsed:

```powershell
.\.venv\Scripts\python -m studio_one_mcp.keyscheme --list Zoom
.\.venv\Scripts\python -m studio_one_mcp.keyscheme --verbose
```

### Resolution order

1. `shortcuts.json`, keyed by the `command` field in `keymap.json`
   (`"Category|Name"`, e.g. `"Edit|Undo"`)
2. the `keys` field in `keymap.json`

Commands with no shortcut assigned in the DAW — adding tracks, for instance —
fall through to step 2.

### Choosing among alternatives

A command may carry several shortcuts. The parser prefers the one least
dependent on keyboard layout: letters, function keys and the numeric keypad
rank above punctuation, which is addressed through `VK_OEM_*` codes that follow
the physical positions of a US keyboard.

*Zoom In* is typically bound to `E`, `Ctrl++` and `Ctrl+NumPad+`; `E` is chosen.
This matters on non-US layouts, where `Ctrl++` lands on a different physical key
and silently does nothing.

### Why the XML rather than the HTML export

The DAW can also export shortcuts as HTML. Both formats carry the same
shortcuts, but:

- the XML gives one element per shortcut; the HTML joins them with `<br>`
- the XML carries internal command names, the HTML display names — these differ
  for roughly a hundred commands (`Toggle Sync Device AbletonLink` versus
  `Toggle Ableton Link`), and control-surface definitions address commands by
  the internal name
- the HTML is a presentation format and can change between releases

Macro names in the XML are Base64-encoded (`Macro QWRkIEVR` is `Add EQ`), which
is worth knowing if macro dispatch is ever added.

## MIDI

Windows cannot create virtual MIDI ports, so the loopback port must exist before
the server starts.

1. Install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) and
   create a port named `StudioOneMCP`.
2. In the DAW: *Preferences → External Devices → Add → Mackie Control Universal*,
   **Receive From** = `StudioOneMCP`.

The port may appear to the system with a numeric suffix (`StudioOneMCP 2`);
matching is by substring, so this is fine. If no matching port exists, the
server reports the available ports rather than crashing.

## Key tokens

`keymap.json` and `shortcuts.json` accept:

| Token | Meaning |
|---|---|
| `a`–`z`, `0`–`9` | letters and digits |
| `f1`–`f24` | function keys |
| `num0`–`num9`, `numplus`, `numminus`, `nummultiply`, `numdivide`, `numdecimal` | numeric keypad |
| `return`, `tab`, `space`, `escape`, `backspace`, `delete`, `insert`, `home`, `end`, `pageup`, `pagedown`, `left`, `right`, `up`, `down`, `capslock` | named keys |
| `,` `-` `.` `=` `;` `/` `` ` `` `[` `]` `\` `'` | punctuation via `VK_OEM_*` (layout-dependent) |
| `vk:0xBB` | raw virtual-key code |
| `ctrl`, `shift`, `alt`, `win` | modifiers |

## Troubleshooting

**No window found** — the title does not match. Set
`STUDIO_ONE_MCP_WINDOW_TITLE` to a substring of the actual title.

**Could not bring the window to the foreground** — usually a privilege
mismatch. Run the MCP client and the DAW at the same elevation level.

**A shortcut with punctuation does nothing** — the OEM code lands on a
different physical key under the active layout. Prefer a keypad or letter
alternative, or write the code directly as `vk:0x...`.

**No MIDI port matching 'StudioOneMCP'** — create the loopback port first; the
error message lists what is available.

## Known limitations

- Not tested on Windows by the author of these changes; the keystroke path in
  particular deserves scrutiny.
- The DAW's Undo-label verification used on macOS has no Windows equivalent, so
  actions are sent without confirmation of effect.
- One shortcut in a typical scheme cannot be translated: `#` bound to
  *All Notes Off*, whose physical position is not determinable from the file.
  Multimedia keys (`Play Pause`, `Record`, `Rewind`, `Forward`, `Stop`) are
  skipped as well; every command using them also has a keypad alternative.
