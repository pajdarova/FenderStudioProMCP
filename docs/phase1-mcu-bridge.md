# Phase 1 — Mackie Control Universal (MCU) MIDI Bridge

## Overview

Phase 1 exposes Studio One controls to an LLM via the Model Context Protocol (MCP). The
transport layer is the **Mackie Control Universal (MCU)** protocol, which Studio One
natively supports as a remote control surface. Commands are sent over a **virtual MIDI
loopback port** that Studio One reads on the same machine.

No Studio One plugin or special build is required. The only prerequisite is that the user
adds the virtual port as an MCU control surface inside Studio One's Options → External
Devices panel.

---

## Architecture

```
LLM / MCP Client
      │  (JSON-RPC over stdio / SSE)
      ▼
┌─────────────────────────┐
│   MCP Server (server.py) │
│   - registers tools      │
│   - validates args       │
└────────────┬────────────┘
             │ Python function calls
             ▼
┌─────────────────────────┐
│   MidiBridge (midi_bridge.py) │
│   - opens virtual port   │
│   - encodes MCU messages │
│   - sends / receives     │
└────────────┬────────────┘
             │ MIDI bytes
             ▼
   Virtual MIDI port  ←──── Studio One (MCU surface)
   (e.g. "StudioOneMCP")
```

---

## MCU Protocol Reference

### Message Types Used

| Control | MIDI Message | Details |
|---------|-------------|---------|
| Play    | Note On ch1, note 94, vel 127 | Release: vel 0 |
| Stop    | Note On ch1, note 93, vel 127 | |
| Record  | Note On ch1, note 95, vel 127 | |
| Rewind  | Note On ch1, note 91, vel 127 | |
| Fast Forward | Note On ch1, note 92, vel 127 | |
| Loop (Cycle) | Note On ch1, note 86, vel 127 | Toggles loop mode |
| Save   | Note On ch1, note 98, vel 127 | |
| Undo   | Note On ch1, note 110, vel 127 | |
| Redo   | Note On ch1, note 101, vel 127 | |
| Channel Mute (ch N) | Note On ch1, note 16+N, vel 127 | N = 0-7 |
| Channel Solo (ch N) | Note On ch1, note 8+N, vel 127 | N = 0-7 |
| Channel Rec Arm (ch N) | Note On ch1, note 0+N, vel 127 | N = 0-7 |
| Channel Select (ch N) | Note On ch1, note 24+N, vel 127 | N = 0-7 |
| Channel Fader (ch N) | Pitch Bend, MIDI ch N+1 | 14-bit, 0–16383 |
| Master Fader | Pitch Bend, MIDI ch 9 | 14-bit, 0–16383 |
| VPot Pan (ch N) | CC 16+N, val 1–63 right / 65–127 left | Relative encoder |
| Master Volume Knob | CC 60, absolute 0–127 | Non-MCU, DAW-specific |

### Fader Scaling

Studio One maps 0 dB to roughly pitch-bend value **8192** (center). Full scale is
16383; minus-infinity is 0. A convenience mapping:

```
dB  →  pitch-bend value
−∞  →  0
−60 →  1024
−12 →  5461
  0 →  8192
 +6 →  10923
+12 →  13653 (near clip)
```

For simplicity the Phase 1 tools accept a **0–100 linear "fader level"** and map it
linearly to 0–16383.

---

## Virtual MIDI Port Setup

### macOS
```bash
# Built-in IAC Driver — open Audio MIDI Setup, add a bus named "StudioOneMCP"
```

### Linux
```bash
sudo modprobe snd-virmidi   # or use JACK / pipewire virtual ports
# Creates /dev/snd/midi* devices; expose one as "StudioOneMCP"
```

### Windows
```
Install loopMIDI (Tobias Erichsen) and create a port named "StudioOneMCP"
```

---

## Studio One Setup

1. Open **Studio One → Options (Preferences on Mac) → External Devices**.
2. Click **Add** → choose **New Control Surface**.
3. Set **Type** to "Mackie Control Universal".
4. Set **Receive From** to the virtual MIDI port (e.g. "StudioOneMCP").
5. Leave **Send To** blank (or point to a second virtual port if you want feedback).
6. Click **OK** and close.

---

## Tools Exposed by the MCP Server

### Transport Tools
| Tool | Description |
|------|-------------|
| `transport_play` | Start playback |
| `transport_stop` | Stop playback |
| `transport_record` | Arm and begin recording |
| `transport_rewind` | Rewind (hold-style, sends press + release) |
| `transport_fast_forward` | Fast forward |
| `transport_toggle_loop` | Toggle loop/cycle mode |
| `transport_save` | Save the current project |
| `transport_undo` | Undo last action |
| `transport_redo` | Redo last undone action |

### Mixer Tools
| Tool | Args | Description |
|------|------|-------------|
| `mixer_set_fader` | `channel` (0-7 or "master"), `level` (0-100) | Set fader position |
| `mixer_toggle_mute` | `channel` (0-7) | Toggle mute on a channel |
| `mixer_toggle_solo` | `channel` (0-7) | Toggle solo on a channel |
| `mixer_toggle_rec_arm` | `channel` (0-7) | Toggle record arm |
| `mixer_select_channel` | `channel` (0-7) | Select/focus a channel |
| `mixer_set_pan` | `channel` (0-7), `pan` (-64 to +63) | Adjust pan (relative encoder) |

---

## Limitations & Mitigations

| Limitation | Mitigation |
|-----------|-----------|
| MCU is command-only — no state readback | Cache last-sent values in `MidiBridge`; report "assumed state" |
| 8-channel strip limit per MCU surface | Future: bank switching (MCU supports up to 8 banks) |
| No project metadata (tempo, track names) | Phase 2 UCNET bridge will provide this |
| Timing-sensitive rapid commands | Add configurable inter-message delay (default 20 ms) |

---

## Running the Server

```bash
pip install -e ".[dev]"

# Start as stdio MCP server (for Claude Desktop / claude CLI)
studio-one-mcp

# Start with SSE transport for web clients
studio-one-mcp --transport sse --port 8765
```

Add to `claude_desktop_config.json`:
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
