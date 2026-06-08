# Studio One Keyboard Shortcut Setup

StudioOneMcp's automation tools send keystrokes to Studio One. Most actions use
Studio One's built-in default shortcuts and work out of the box. A few actions
that don't have defaults need a one-time manual assignment.

## One-time setup

1. Open Studio One
2. Go to **Studio One → Preferences** (macOS) or **Options** (Windows)
3. Click **Keyboard Shortcuts**
4. Use the search box to find each action below and assign the listed shortcut

| Action | Search for | Mac shortcut | Windows shortcut |
|--------|-----------|-------------|-----------------|
| `auto_add_instrument_track` | "Add Instrument Track" | `Ctrl+Shift+Cmd+I` | `Ctrl+Shift+Alt+I` |
| `auto_add_bus_track` | "Add Bus Channel" | `Ctrl+Shift+Cmd+B` | `Ctrl+Shift+Alt+B` |

All other automation tools use Studio One's existing default shortcuts — no
additional setup required.

## Built-in shortcuts used

| Tool | Default shortcut | Action |
|------|-----------------|--------|
| `auto_add_audio_track` | `T` + Enter | Add audio track (dialog default) |
| `auto_duplicate_track` | `Cmd/Ctrl+D` | Duplicate track |
| `auto_delete_selected` | `Backspace` / `Delete` | Delete selection |
| `auto_undo` | `Cmd/Ctrl+Z` | Undo |
| `auto_redo` | `Cmd/Ctrl+Shift+Z` | Redo |
| `auto_save` | `Cmd/Ctrl+S` | Save |
| `auto_toggle_mixer` | `F3` | Toggle mixer |
| `auto_toggle_browser` | `F5` | Toggle browser |
| `auto_toggle_editor` | `F2` | Toggle editor |
| `auto_select_all` | `Cmd/Ctrl+A` | Select all |
| `auto_zoom_in` | `Ctrl+=` | Zoom in |
| `auto_zoom_out` | `Ctrl+-` | Zoom out |
| `auto_zoom_to_fit` | `Shift+F` | Zoom to fit |
| `auto_toggle_loop` | `Cmd/Ctrl+L` | Toggle loop |
| `auto_go_to_start` | `Home` | Go to start |
| `auto_go_to_end` | `End` | Go to end |
| `auto_split_at_playhead` | `S` | Split at playhead |
| `auto_quantize` | `Q` | Quantize |

## Customising the mapping

Edit `src/studio_one_mcp/keymap.json` (or point `STUDIO_ONE_MCP_KEYMAP` to
your own copy) to remap any action. The structure is:

```json
{
  "actions": {
    "my_action": {
      "description": "...",
      "mac":     {"keys": ["cmd+shift+x"]},
      "windows": {"keys": ["ctrl+shift+x"]},
      "linux":   {"keys": ["ctrl+shift+x"]}
    }
  }
}
```

For actions that open a dialog and need a confirmation keypress:

```json
{
  "keys": ["t"],
  "delay_ms": 350,
  "dialog": {"confirm": ["return"]}
}
```

`delay_ms` is how long to wait before sending the confirm key (gives the dialog
time to open). Set `STUDIO_ONE_MCP_KEYMAP=/path/to/your/keymap.json` to use a
custom file without modifying the package.
