# Setup

StudioOneMcp controls Studio One through three push-based mechanisms. You only
need to set up the ones you want to use — **keyboard automation alone covers
most actions** and is the quickest to get running.

| Path | What it does | Setup |
|------|--------------|-------|
| **Keyboard automation** | Most actions: tracks, transport, save/undo, zoom, panels, split, quantize | One Accessibility toggle |
| **Macros** | Commands with no shortcut (e.g. insert a plugin) | None |
| **MCU MIDI** *(optional)* | Continuous control: faders, pan, mute/solo, transport | Virtual MIDI port + Mackie surface |

---

## 1. Install the server

```bash
git clone https://github.com/tiwadara/StudioOneMcp
cd StudioOneMcp
pip install -e .
```

Add it to your MCP client (e.g. Claude Desktop —
`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "studio-one": { "command": "studio-one-mcp" }
  }
}
```

---

## 2. Keyboard automation — the main path (1 permission)

The server sends keyboard shortcuts to Studio One via macOS. This needs
**Accessibility** permission for the app that runs the server.

1. Open **System Settings → Privacy & Security → Accessibility**.
2. Turn **on** the app that launches the MCP server — usually your MCP client
   (e.g. **Claude**), or your terminal if you run `studio-one-mcp` manually.
   - If it isn't listed, click **+**, add the app, then toggle it on.
3. **Quit and reopen that app** so the permission takes effect.

That's it — actions like add track, save, undo, zoom, and transport now work.

> macOS attributes the permission to whichever app is the parent of the
> `osascript` call. If keystrokes silently do nothing, double-check that the
> *exact* app running the server is the one toggled on.

### Optional custom shortcuts

A few actions have no Studio One default. Assign these once in
**Studio One → Preferences → Keyboard Shortcuts** if you want them:

| Tool | Search for | Suggested shortcut (Mac) |
|------|-----------|--------------------------|
| `auto_add_instrument_track` | "Add Instrument Track" | `Ctrl+Shift+Cmd+I` |
| `auto_add_bus_track` | "Add Bus Channel" | `Ctrl+Shift+Cmd+B` |
| `auto_add_audio_track_mono` | "Add Audio Track (mono)" | `Ctrl+Shift+Cmd+M` |

All other keyboard tools use Studio One's built-in defaults — no setup needed.

---

## 3. Macros — for commands with no shortcut (no permission)

`auto_generate_insert_macro` and friends write a `.studioonemacro` file to
`~/Documents/Studio One/Macros/MCP/`. To use a generated macro:

1. Run the tool (it writes the file).
2. In Studio One: **Studio One menu → Macros → Reload Macros**.
3. The macro appears in the macro toolbar under the **MCP** group — click it,
   or assign it a shortcut in **Preferences → Keyboard Shortcuts → Macros**.

No permissions required — Studio One watches the Macros folder itself.

---

## 4. MCU MIDI — optional, for faders & real-time control (no Accessibility)

This path uses MIDI instead of keystrokes, so it needs **no Accessibility
permission** — but only covers transport and mixer (faders, pan, mute, solo,
track select).

1. Create a virtual MIDI port named **`StudioOneMCP`**:
   - **macOS**: *Audio MIDI Setup → Window → Show MIDI Studio → double-click
     **IAC Driver** → enable "Device is online" → add a port/bus.* Name it
     `StudioOneMCP`.
2. In Studio One: **Preferences → External Devices → Add → New Control Surface**
   - **Type** = `Mackie Control Universal`
   - **Receive From** = `StudioOneMCP`
3. Click **OK**.

The `transport_*` and `mixer_*` tools now drive Studio One over MIDI.

---

## Quick check

With Studio One open, ask your MCP client to run `auto_new_song` (or
`auto_save`). If a dialog appears / the song saves, keyboard automation is
working.
