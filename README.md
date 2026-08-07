# FenderStudioProMCP

**Control PreSonus Studio One with an LLM** — an MCP (Model Context Protocol) server that
turns Studio One into an AI-controllable DAW instrument. Aimed at **production** workflows
(editing, MIDI manipulation, mixing, effects, export), with a longer-term vision of
AI-assisted **live-set** control.

> Community project, work in progress. Not affiliated with or endorsed by PreSonus.

---

## How it controls Studio One

Studio One has no public remote-control API, so FenderStudioProMCP drives it through four
complementary, **push-based** paths — each proven to work on Studio One 7 (macOS):

| Path | What it does | Needs |
|---|---|---|
| **MIDI → command dispatch** ⭐ | A user control-surface (`StudioOneMCP Pads`) maps MIDI CCs/notes to Studio One **commands and macros**. The MCP sends MIDI on a virtual port → the command fires. Reliable, no Accessibility. | Virtual port + surface bound to *Receive From* |
| **MCU MIDI** | Faders, pan, mute, solo, transport via the built-in Mackie Control Universal surface | Virtual port + MCU surface |
| **Menu / keyboard automation** | Clicks Studio One menu items and sends shortcuts via macOS System Events; verifies actions via the Edit▸Undo label | macOS Accessibility |
| **Macro generation** | Writes `.studioonemacro` files for command sequences with no shortcut | Nothing |

⭐ **The MIDI → command path is the backbone.** It's confirmed working: the MCP sends a CC
on the `StudioOneMCP` virtual port and Studio One fires the mapped command (e.g. *Add Audio
Track*, verified via the Edit▸Undo label). Every Studio One command and every installed
macro can be reached this way — see the catalog below.

---

## Function catalog

Studio One's command surface is enumerated into [`docs/function-catalog.json`](docs/function-catalog.json):

- **194 built-in commands** (Edit, Event, Audio, Transport, Track, Song, File, View — top level)
- **221 macros** (the installed macro library — quantize, humanize, velocity, articulations, chords, tempo, add-EQ/compressor, export, …)
- **= 415 functions**, mappable to MIDI (notes/CCs × 16 channels ≈ 2000 slots)

Mapping all 415 to MIDI + exposing them as named MCP tools is the current build — see
[Issues](../../issues).

---

## Setup

### 1. Install
```bash
git clone https://github.com/pajdarova/FenderStudioProMCP
cd FenderStudioProMCP
python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
```

### 2. Virtual MIDI port
FenderStudioProMCP opens a virtual port named **`StudioOneMCP`** (pinned to a fixed uniqueID so
Studio One re-binds to it every launch). Just run the server — the port appears. (On
Windows/Linux, use a loopback such as loopMIDI / `snd-virmidi` named `StudioOneMCP`.)

### 3. Install the control surface (MIDI → command)
Copy `studio-one-devices/StudioOneMCPPads/` into your Studio One **User Devices** folder:
```
~/Library/Application Support/PreSonus/Studio One 7/User Devices/StudioOneMCPPads/
```
Then in **Studio One ▸ Settings ▸ External Devices ▸ Add…** pick **StudioOneMCP ▸
StudioOneMCP Pads**, and set **Receive From = `StudioOneMCP`**. Leave **Send To** empty
(the surface is receive-only). Relaunch Studio One so it scans the device.

### 4. (Optional) MCU surface for faders/transport
External Devices ▸ Add ▸ **Mackie Control Universal** ▸ Receive From = `StudioOneMCP`.

### 5. (Optional) Accessibility for menu/keyboard automation
System Settings ▸ Privacy & Security ▸ **Accessibility** → enable your MCP host app.

### 6. Add to your MCP client (e.g. Claude Desktop)
```json
{
  "mcpServers": {
    "studio-pro": { "command": "studio-pro-mcp", "args": ["--port-name", "StudioOneMCP"] }
  }
}
```

---

## Available tools (current)

- **`studio_one_run_command(name)`** ⭐ — fire **any of 224 built-in Studio One commands** by name (Edit, Track, Event, Audio, Song, Transport, Zoom, Show, Arranger, …). Case-insensitive, unique partial match accepted. e.g. `"Duplicate"`, `"Split Range"`, `"Find Track"`, `"Bounce Selection"`. **Verified working end-to-end.**
- **`studio_one_list_commands(filter)`** — discover command names.
- **Transport:** play · stop · record · rewind · fast-forward · toggle-loop · save · undo · redo
- **Mixer (MCU):** set-fader · toggle-mute · toggle-solo · toggle-rec-arm · select-channel · set-pan
- **Automation:** add tracks · new song · save-as · toggle mixer/browser/editor · zoom · split · …
- **Macros:** generate `.studioonemacro` sequences

> **Note:** the 224 mapped commands are Studio One *built-ins* (they dispatch from a control surface). User **macros** (139 in `docs/macros-todo.json`) do **not** dispatch from a surface — they need a keyboard/Command-Bar trigger, tracked in [#3](../../issues/3).

---

## Architecture

```
LLM / MCP client
   │ JSON-RPC (stdio)
   ▼
MCP server (server.py) ── tool registration, arg validation
   │
   ├─ MidiBridge (midi_bridge.py) ─┐
   │   MCU + CC command dispatch   │  virtual port "StudioOneMCP"
   ├─ CoreMIDI pin (coremidi.py) ──┘  (pinned uniqueID)  ──► Studio One
   │                                       surfaces: StudioOneMCP Pads (commands), MCU (mixer)
   ├─ Automation (keystrokes.py)  ──► System Events (menus / shortcuts)
   └─ Macro writer (macro_writer.py) ──► ~/Documents/Studio One/Macros
```

---

## Roadmap

Tracked in [GitHub Issues](../../issues). Highlights:
- Expand the pad surface to the full MIDI → function map (all 415)
- Named MCP tools to trigger any function ("quantize to 1/16", "add EQ + comp", "export stems")
- **Vision:** AI DAW-controller for autonomous mixing — songs, faders, effects, transitions
- Feedback/sensing (MCU meters, state model) for level-aware decisions

## Development
```bash
pytest ; ruff check src tests ; mypy src
```

## Credits

FenderStudioProMCP began as a fork of
[tiwadara/StudioOneMcp](https://github.com/tiwadara/StudioOneMcp) (MIT
licensed), which established the MIDI/MCU control-surface approach to driving
Studio One from an MCP server. This repository has since been substantially
rewritten: Windows support, adaptation to the Fender Studio Pro rebrand, an
MCP SDK 2.0 upgrade with dual stdio/HTTP transport, and a command catalog
generated per-user from `.keyscheme` exports.

## License
MIT — see [LICENSE](LICENSE).
