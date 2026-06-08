"""MCP tools for OS-level Studio One automation via keyboard shortcuts."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from studio_one_mcp.keystrokes import KeystrokeError, send_action

# ---------------------------------------------------------------------------
# Tool → keymap action mapping
# ---------------------------------------------------------------------------

_TOOL_ACTION: dict[str, str] = {
    "auto_add_audio_track":      "add_audio_track",
    "auto_add_instrument_track": "add_instrument_track",
    "auto_add_bus_track":        "add_bus_track",
    "auto_duplicate_track":      "duplicate_track",
    "auto_delete_selected":      "delete_selected",
    "auto_undo":                 "undo",
    "auto_redo":                 "redo",
    "auto_save":                 "save",
    "auto_save_as":              "save_as",
    "auto_new_song":             "new_song",
    "auto_toggle_mixer":         "toggle_mixer",
    "auto_toggle_browser":       "toggle_browser",
    "auto_toggle_editor":        "toggle_editor",
    "auto_select_all":           "select_all",
    "auto_zoom_in":              "zoom_in",
    "auto_zoom_out":             "zoom_out",
    "auto_zoom_to_fit":          "zoom_to_fit",
    "auto_toggle_loop":          "toggle_loop",
    "auto_go_to_start":          "go_to_start",
    "auto_go_to_end":            "go_to_end",
    "auto_split_at_playhead":    "split_at_playhead",
    "auto_quantize":             "quantize",
    "auto_add_audio_track_mono": "add_audio_track_mono",
}

_NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}, "required": []}


def _automation_tools() -> list[Tool]:
    return [
        Tool(
            name="auto_add_audio_track",
            description="Add a new audio track to the current song.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_add_instrument_track",
            description=(
                "Add a new instrument track. "
                "Requires a custom shortcut (Ctrl+Shift+Cmd+I) assigned once in "
                "Studio One Preferences → Keyboard Shortcuts."
            ),
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_add_bus_track",
            description=(
                "Add a bus/FX channel. "
                "Requires a custom shortcut (Ctrl+Shift+Cmd+B) assigned in Preferences."
            ),
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_duplicate_track",
            description="Duplicate the currently selected track.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_delete_selected",
            description="Delete the currently selected track or event.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_undo",
            description="Undo the last action in Studio One.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_redo",
            description="Redo the last undone action in Studio One.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_save",
            description="Save the current song.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_save_as",
            description="Open the Save As dialog for the current song.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_new_song",
            description="Open the New Song dialog in Studio One.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_toggle_mixer",
            description="Show or hide the Studio One Mixer panel (F3).",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_toggle_browser",
            description="Show or hide the Studio One Browser panel (F5).",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_toggle_editor",
            description="Show or hide the Piano Roll / Audio Editor (F2).",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_select_all",
            description="Select all tracks or events in the current context.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_zoom_in",
            description="Zoom in on the arrangement timeline.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_zoom_out",
            description="Zoom out on the arrangement timeline.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_zoom_to_fit",
            description="Zoom to fit all content in the arrangement view.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_toggle_loop",
            description="Toggle loop (cycle) playback on or off.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_go_to_start",
            description="Move the playhead to the start of the song.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_go_to_end",
            description="Move the playhead to the end of the song.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_split_at_playhead",
            description="Split selected event(s) at the current playhead position.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_quantize",
            description="Quantize selected MIDI notes to the current quantize grid.",
            inputSchema=_NO_ARGS,
        ),
        Tool(
            name="auto_add_audio_track_mono",
            description=(
                "Add a new mono audio track directly without the Add Track dialog. "
                "Requires a custom shortcut (Ctrl+Shift+Cmd+M on Mac) assigned once in "
                "Studio One Preferences → Keyboard Shortcuts → Track → 'Add Audio Track (mono)'."
            ),
            inputSchema=_NO_ARGS,
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(name: str, _arguments: dict[str, Any]) -> list[TextContent]:
    if name not in _TOOL_ACTION:
        raise ValueError(f"Unknown automation tool: {name!r}")

    action = _TOOL_ACTION[name]
    try:
        await send_action(action)
        return [TextContent(type="text", text=f"OK: sent '{action}' to Studio One")]
    except KeystrokeError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]
