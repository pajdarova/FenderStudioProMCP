"""MCP tools that require a live UCNET connection for real state readback.

These tools are only registered when the server is started with --ucnet-host.
Without UCNET, transport and mixer are still available via the MCU MIDI bridge,
but state-query tools are not exposed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from studio_one_mcp.ucnet.client import UCNETClient, UCNETError

log = logging.getLogger(__name__)

# Known parameter paths (preliminary — subject to revision after captures)
_PATH_TEMPO = "/transport/tempo"
_PATH_IS_PLAYING = "/transport/isPlaying"
_PATH_IS_RECORDING = "/transport/isRecording"
_PATH_POSITION = "/transport/positionBars"

_FADER_PATH = "/mixer/channel[{ch}]/fader"
_MUTE_PATH = "/mixer/channel[{ch}]/mute"
_SOLO_PATH = "/mixer/channel[{ch}]/solo"
_NAME_PATH = "/mixer/channel[{ch}]/name"


def _fader_path(ch: int) -> str:
    return _FADER_PATH.format(ch=ch)


def _mute_path(ch: int) -> str:
    return _MUTE_PATH.format(ch=ch)


def _solo_path(ch: int) -> str:
    return _SOLO_PATH.format(ch=ch)


def _name_path(ch: int) -> str:
    return _NAME_PATH.format(ch=ch)


# ---------------------------------------------------------------------------
# Tool catalogue
# ---------------------------------------------------------------------------

def _ucnet_tools() -> list[Tool]:
    channel_schema = {
        "type": "integer",
        "description": "Channel strip index (0-based).",
        "minimum": 0,
    }
    return [
        Tool(
            name="ucnet_get_transport_state",
            description=(
                "Return the current transport state from Studio One via UCNET: "
                "tempo, playback position, isPlaying, and isRecording flags. "
                "Requires --ucnet-host."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="ucnet_get_channel_state",
            description=(
                "Return the current state of a mixer channel from Studio One via UCNET: "
                "fader level, mute, solo, and channel name. "
                "Requires --ucnet-host."
            ),
            inputSchema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="ucnet_set_fader",
            description=(
                "Set a mixer channel fader to an exact level (0.0 = −∞ dB, 1.0 = 0 dB) "
                "using UCNET for precise parameter control. "
                "Requires --ucnet-host."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": channel_schema,
                    "level": {
                        "type": "number",
                        "description": "Fader level 0.0–1.0 (linear amplitude).",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
                "required": ["channel", "level"],
            },
        ),
        Tool(
            name="ucnet_set_mute",
            description=(
                "Explicitly mute or unmute a mixer channel via UCNET. "
                "Requires --ucnet-host."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": channel_schema,
                    "muted": {
                        "type": "boolean",
                        "description": "True to mute, False to unmute.",
                    },
                },
                "required": ["channel", "muted"],
            },
        ),
        Tool(
            name="ucnet_get_full_state",
            description=(
                "Dump the full cached UCNET parameter state as JSON. "
                "Useful for debugging and discovering available parameter paths. "
                "Requires --ucnet-host."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(name: str, arguments: dict[str, Any], client: UCNETClient) -> list[TextContent]:
    match name:
        case "ucnet_get_transport_state":
            state = {
                "tempo": client.get_parameter(_PATH_TEMPO),
                "isPlaying": client.get_parameter(_PATH_IS_PLAYING),
                "isRecording": client.get_parameter(_PATH_IS_RECORDING),
                "position": client.get_parameter(_PATH_POSITION),
            }
            return [TextContent(type="text", text=json.dumps(state, indent=2))]

        case "ucnet_get_channel_state":
            ch = int(arguments["channel"])
            state = {
                "channel": ch,
                "name": client.get_parameter(_name_path(ch)),
                "fader": client.get_parameter(_fader_path(ch)),
                "mute": client.get_parameter(_mute_path(ch)),
                "solo": client.get_parameter(_solo_path(ch)),
            }
            return [TextContent(type="text", text=json.dumps(state, indent=2))]

        case "ucnet_set_fader":
            ch = int(arguments["channel"])
            level = float(arguments["level"])
            log.info("UCNET: set_fader(channel=%d, level=%.3f)", ch, level)
            try:
                await client.set_parameter(_fader_path(ch), level)
            except UCNETError as exc:
                return [TextContent(type="text", text=f"ERROR: {exc}")]
            return [TextContent(type="text", text=f"OK: channel {ch} fader → {level:.3f}")]

        case "ucnet_set_mute":
            ch = int(arguments["channel"])
            muted = bool(arguments["muted"])
            log.info("UCNET: set_mute(channel=%d, muted=%s)", ch, muted)
            try:
                await client.set_parameter(_mute_path(ch), int(muted))
            except UCNETError as exc:
                return [TextContent(type="text", text=f"ERROR: {exc}")]
            return [TextContent(type="text", text=f"OK: channel {ch} mute → {'ON' if muted else 'OFF'}")]

        case "ucnet_get_full_state":
            snapshot = client.get_state_snapshot()
            return [TextContent(type="text", text=json.dumps(snapshot, indent=2))]

        case _:
            raise ValueError(f"Unknown UCNET tool: {name!r}")
