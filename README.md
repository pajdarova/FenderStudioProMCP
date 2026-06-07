# StudioOneMcp

An MCP (Model Context Protocol) server that lets an LLM control PreSonus Studio One
via the **Mackie Control Universal (MCU)** protocol over a virtual MIDI port.

## Quick Start

### 1. Prerequisites

- Studio One 5 or later
- Python 3.10+
- A virtual MIDI loopback port named **`StudioOneMCP`**
  - **macOS**: Use the built-in IAC Driver (Audio MIDI Setup → IAC Driver → add bus)
  - **Linux**: `sudo modprobe snd-virmidi` or use loopMIDI-compatible tool
  - **Windows**: Install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)

### 2. Configure Studio One

1. Open **Options → External Devices** (macOS: **Preferences → External Devices**)
2. Click **Add** → **New Control Surface**
3. Set **Type** = `Mackie Control Universal`
4. Set **Receive From** = `StudioOneMCP`
5. Click **OK**

### 3. Install the Server

```bash
pip install studio-one-mcp
# or from source:
git clone https://github.com/tiwadara/studioonemcp
cd studioonemcp
pip install -e ".[dev]"
```

### 4. Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "studio-one": {
      "command": "studio-one-mcp",
      "args": ["--port-name", "StudioOneMCP"]
    }
  }
}
```

Restart Claude Desktop, open a Studio One project, and start talking to your DAW.

---

## Available Tools

### Transport

| Tool | Description |
|------|-------------|
| `transport_play` | Start playback |
| `transport_stop` | Stop playback |
| `transport_record` | Start recording |
| `transport_rewind` | Rewind |
| `transport_fast_forward` | Fast forward |
| `transport_toggle_loop` | Toggle loop/cycle mode |
| `transport_save` | Save the current project |
| `transport_undo` | Undo last action |
| `transport_redo` | Redo last undone action |

### Mixer

| Tool | Args | Description |
|------|------|-------------|
| `mixer_set_fader` | `channel` (0–7 or `"master"`), `level` (0–100) | Set fader level |
| `mixer_toggle_mute` | `channel` (0–7) | Toggle channel mute |
| `mixer_toggle_solo` | `channel` (0–7) | Toggle channel solo |
| `mixer_toggle_rec_arm` | `channel` (0–7) | Toggle record arm |
| `mixer_select_channel` | `channel` (0–7) | Select/focus a channel strip |
| `mixer_set_pan` | `channel` (0–7), `pan` (−64 to +63) | Adjust pan position |

---

## Architecture

```
LLM / MCP Client
      │  (JSON-RPC over stdio or SSE)
      ▼
MCP Server (server.py)     ← tool registration, arg validation
      │
MidiBridge (midi_bridge.py) ← MCU MIDI encoding, virtual port management
      │
Virtual MIDI port  ──────────────────► Studio One (MCU surface)
```

See [docs/phase1-mcu-bridge.md](docs/phase1-mcu-bridge.md) for the full MCU protocol
reference and setup details.

---

## Roadmap

- **Phase 1** ✅ — MCU MIDI bridge (transport + 8-channel mixer)
- **Phase 2** — UCNET protocol integration for full bidirectional state access
  (track names, plugin parameters, tempo, markers). See [docs/phase2-ucnet.md](docs/phase2-ucnet.md).

---

## Development

```bash
# Run tests
pytest

# Lint
ruff check src tests

# Type check
mypy src
```

## License

MIT
