"""MCP tools for firing any built-in Studio One command by name.

Resolves a function name against ``docs/midi-map.json`` and sends its CC on the
``StudioOneMCP`` virtual port, where the ``StudioOneMCP Pads`` surface turns it into
a Studio One ``<Command>``. Built-in commands only — user macros need a different
trigger (see docs/macros-todo.json).
"""

from __future__ import annotations

import logging

from mcp.types import TextContent, Tool

from studio_one_mcp import commands as cmd
from studio_one_mcp.midi_bridge import MidiBridge

log = logging.getLogger(__name__)


def _command_tools() -> list[Tool]:
    return [
        Tool(
            name="studio_one_run_command",
            description=(
                "Run any built-in Studio One command by name — e.g. 'Duplicate', "
                "'Split Range', 'Quantize', 'Find Track', 'Bounce Selection'. "
                "Case-insensitive; a unique partial match is accepted. "
                "Use studio_one_list_commands to discover names."
            ),
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Command name"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="studio_one_list_commands",
            description="List available Studio One commands, optionally filtered by a search term.",
            input_schema={
                "type": "object",
                "properties": {"filter": {"type": "string", "description": "Substring filter"}},
                "required": [],
            },
        ),
    ]


async def _dispatch(name: str, arguments: dict, bridge: MidiBridge) -> list[TextContent]:
    cmap = cmd.load_map()

    if name == "studio_one_list_commands":
        flt = (arguments.get("filter") or "").strip().lower()
        items = [f["label"] for f in cmap if flt in f["label"].lower()]
        body = "\n".join(f"- {x}" for x in items) if items else "(no matches)"
        return [TextContent(type="text", text=f"{len(items)} command(s):\n{body}")]

    # studio_one_run_command
    fname = arguments.get("name", "")
    match = cmd.resolve(fname, cmap)
    if match is None:
        return [TextContent(type="text", text=f"ERROR: no command matching {fname!r}")]
    if isinstance(match, list):
        cands = ", ".join(x["label"] for x in match[:10])
        return [TextContent(type="text", text=f"Ambiguous {fname!r}. Candidates: {cands}")]
    bridge.press_cc(match["cc"], match["channel"])
    return [TextContent(type="text", text=f"Ran '{match['label']}' [{match['category']}]")]
