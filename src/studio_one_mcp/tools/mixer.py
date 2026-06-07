"""MCP tools for Studio One mixer control (faders, mute, solo, pan, etc.)."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from studio_one_mcp.midi_bridge import MidiBridge

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool catalogue
# ---------------------------------------------------------------------------

def _mixer_tools() -> list[Tool]:
    channel_schema = {
        "type": "integer",
        "description": "Channel strip index (0 = first track, 7 = eighth track).",
        "minimum": 0,
        "maximum": 7,
    }
    return [
        Tool(
            name="mixer_set_fader",
            description=(
                "Set the fader level of a mixer channel or the master fader. "
                "Level 0 = minimum (−∞ dB), 100 = maximum (+12 dB), ~75 ≈ 0 dB."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "oneOf": [
                            {**channel_schema},
                            {
                                "type": "string",
                                "enum": ["master"],
                                "description": "Pass 'master' to control the master fader.",
                            },
                        ],
                        "description": "Channel strip (0–7) or 'master'.",
                    },
                    "level": {
                        "type": "number",
                        "description": "Fader position 0–100.",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
                "required": ["channel", "level"],
            },
        ),
        Tool(
            name="mixer_toggle_mute",
            description="Toggle the mute button on a mixer channel strip.",
            inputSchema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_toggle_solo",
            description="Toggle the solo button on a mixer channel strip.",
            inputSchema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_toggle_rec_arm",
            description="Toggle the record-arm button on a mixer channel strip.",
            inputSchema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_select_channel",
            description="Select (focus) a mixer channel strip in Studio One.",
            inputSchema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_set_pan",
            description=(
                "Adjust the pan position of a channel via the MCU VPot encoder. "
                "pan=0 sends a center/reset tick; positive values pan right, negative pan left. "
                "Range −64 to +63."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": channel_schema,
                    "pan": {
                        "type": "integer",
                        "description": "Pan offset −64 (hard left) to +63 (hard right). 0 = center.",
                        "minimum": -64,
                        "maximum": 63,
                    },
                },
                "required": ["channel", "pan"],
            },
        ),
        Tool(
            name="mixer_get_state",
            description=(
                "Return the optimistic (last-sent) mixer state cached by the MCP server. "
                "Because MCU is write-only, these values reflect commands sent, not confirmed DAW state."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(name: str, arguments: dict[str, Any], bridge: MidiBridge) -> list[TextContent]:
    match name:
        case "mixer_set_fader":
            channel = arguments["channel"]
            level = float(arguments["level"])
            log.info("Mixer: set_fader(channel=%r, level=%s)", channel, level)
            bridge.set_fader(channel, level)
            return [TextContent(type="text", text=f"OK: fader channel {channel!r} set to {level:.1f}")]

        case "mixer_toggle_mute":
            ch = int(arguments["channel"])
            log.info("Mixer: toggle_mute(channel=%d)", ch)
            bridge.toggle_mute(ch)
            state = bridge.get_assumed_state()
            muted = state["mute"].get(ch, False)
            return [TextContent(type="text", text=f"OK: channel {ch} mute {'ON' if muted else 'OFF'} (assumed)")]

        case "mixer_toggle_solo":
            ch = int(arguments["channel"])
            log.info("Mixer: toggle_solo(channel=%d)", ch)
            bridge.toggle_solo(ch)
            state = bridge.get_assumed_state()
            soloed = state["solo"].get(ch, False)
            return [TextContent(type="text", text=f"OK: channel {ch} solo {'ON' if soloed else 'OFF'} (assumed)")]

        case "mixer_toggle_rec_arm":
            ch = int(arguments["channel"])
            log.info("Mixer: toggle_rec_arm(channel=%d)", ch)
            bridge.toggle_rec_arm(ch)
            state = bridge.get_assumed_state()
            armed = state["rec_arm"].get(ch, False)
            return [TextContent(type="text", text=f"OK: channel {ch} rec-arm {'ON' if armed else 'OFF'} (assumed)")]

        case "mixer_select_channel":
            ch = int(arguments["channel"])
            log.info("Mixer: select_channel(channel=%d)", ch)
            bridge.select_channel(ch)
            return [TextContent(type="text", text=f"OK: channel {ch} selected")]

        case "mixer_set_pan":
            ch = int(arguments["channel"])
            pan = int(arguments["pan"])
            log.info("Mixer: set_pan(channel=%d, pan=%d)", ch, pan)
            bridge.set_pan(ch, pan)
            direction = "right" if pan > 0 else "left" if pan < 0 else "center"
            return [TextContent(type="text", text=f"OK: channel {ch} pan nudged {abs(pan)} ticks {direction}")]

        case "mixer_get_state":
            state = bridge.get_assumed_state()
            return [TextContent(type="text", text=json.dumps(state, indent=2))]

        case _:
            raise ValueError(f"Unknown mixer tool: {name!r}")
