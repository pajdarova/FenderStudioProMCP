"""MCP tools for Studio One mixer control (faders, mute, solo, pan, etc.)."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from studio_pro_mcp.midi_bridge import MidiBridge

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
                "Level 0 = minimum (−∞ dB), 100 = maximum (+10 dB), 76 ≈ 0 dB, "
                "61.6 ≈ −6 dB, 49.6 ≈ −12 dB, 40 ≈ −20 dB (measured on a real "
                "installation 2026-08-08; below −20 dB not yet calibrated)."
            ),
            input_schema={
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
            input_schema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_toggle_solo",
            description="Toggle the solo button on a mixer channel strip.",
            input_schema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_toggle_rec_arm",
            description="Toggle the record-arm button on a mixer channel strip.",
            input_schema={
                "type": "object",
                "properties": {"channel": channel_schema},
                "required": ["channel"],
            },
        ),
        Tool(
            name="mixer_select_channel",
            description="Select (focus) a mixer channel strip in Studio One.",
            input_schema={
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
            input_schema={
                "type": "object",
                "properties": {
                    "channel": channel_schema,
                    "pan": {
                        "type": "integer",
                        "description": "Pan offset −63 (hard left) to +63 (hard right). 0 = center.",
                        "minimum": -63,
                        "maximum": 63,
                    },
                },
                "required": ["channel", "pan"],
            },
        ),
        Tool(
            name="mixer_get_state",
            description=(
                "Return the mixer state cached by the MCP server. Fader levels are "
                "confirmed values when Studio One echoes fader position back over MIDI, "
                "falling back to the last value this server sent otherwise. Mute/solo/"
                "rec-arm are always optimistic (last commands sent, not confirmed DAW state) "
                "— MCU as implemented here doesn't parse their feedback messages."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="mixer_bank_left",
            description=(
                "Shift the MCU fader bank one step left (show the previous 8 channels). "
                "Has no effect if already at bank 0 (channels 1–8)."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="mixer_bank_right",
            description=(
                "Shift the MCU fader bank one step right (show the next 8 channels). "
                "Has no effect if already at the last bank."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="mixer_goto_bank",
            description=(
                "Jump directly to a specific MCU bank (0–7), where bank 0 = channels 1–8, "
                "bank 1 = channels 9–16, … bank 7 = channels 57–64."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "bank": {
                        "type": "integer",
                        "description": "Target bank number 0–7.",
                        "minimum": 0,
                        "maximum": 7,
                    },
                },
                "required": ["bank"],
            },
        ),
        Tool(
            name="mixer_get_bank",
            description=(
                "Return the current MCU bank number and the absolute channel range it shows."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
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

        case "mixer_bank_left":
            moved = bridge.bank_left()
            if moved:
                return [TextContent(type="text", text=f"OK: bank → {bridge.current_bank} (ch {bridge.channel_offset + 1}–{bridge.channel_offset + 8})")]
            return [TextContent(type="text", text="Already at bank 0 (channels 1–8)")]

        case "mixer_bank_right":
            moved = bridge.bank_right()
            if moved:
                return [TextContent(type="text", text=f"OK: bank → {bridge.current_bank} (ch {bridge.channel_offset + 1}–{bridge.channel_offset + 8})")]
            return [TextContent(type="text", text="Already at last bank (channels 57–64)")]

        case "mixer_goto_bank":
            bank = int(arguments["bank"])
            bridge.goto_bank(bank)
            return [TextContent(type="text", text=f"OK: bank → {bridge.current_bank} (ch {bridge.channel_offset + 1}–{bridge.channel_offset + 8})")]

        case "mixer_get_bank":
            b = bridge.current_bank
            lo = bridge.channel_offset + 1
            hi = bridge.channel_offset + 8
            return [TextContent(type="text", text=f"Bank {b}: channels {lo}–{hi}")]

        case _:
            raise ValueError(f"Unknown mixer tool: {name!r}")
