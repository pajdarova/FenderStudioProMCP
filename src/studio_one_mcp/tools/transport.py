"""MCP tools for Studio One transport control (play, stop, record, etc.)."""

from __future__ import annotations

import logging

from mcp.types import TextContent, Tool

from studio_one_mcp.midi_bridge import MidiBridge

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool catalogue
# ---------------------------------------------------------------------------

def _transport_tools() -> list[Tool]:
    return [
        Tool(
            name="transport_play",
            description="Start playback in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_stop",
            description="Stop playback in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_record",
            description="Start recording in Studio One (arms and rolls transport).",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_rewind",
            description="Rewind the transport position in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_fast_forward",
            description="Fast-forward the transport position in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_toggle_loop",
            description="Toggle loop (cycle) mode on or off in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_save",
            description="Save the current Studio One project.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_undo",
            description="Undo the last action in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="transport_redo",
            description="Redo the last undone action in Studio One.",
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, str] = {
    "transport_play": "play",
    "transport_stop": "stop",
    "transport_record": "record",
    "transport_rewind": "rewind",
    "transport_fast_forward": "fast_forward",
    "transport_toggle_loop": "toggle_loop",
    "transport_save": "save",
    "transport_undo": "undo",
    "transport_redo": "redo",
}


async def _dispatch(name: str, _arguments: dict[str, object], bridge: MidiBridge) -> list[TextContent]:
    method_name = _HANDLERS.get(name)
    if method_name is None:
        raise ValueError(f"Unknown transport tool: {name!r}")

    method = getattr(bridge, method_name)
    log.info("Transport: %s()", method_name)
    method()
    return [TextContent(type="text", text=f"OK: {name} sent via MCU MIDI")]
