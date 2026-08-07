"""MCP tool for generating the command catalog from a .keyscheme export.

Every user's set of installed macros differs, so the catalog cannot be shipped
as a static file — it has to be generated from *that user's* exported
.keyscheme. This tool lets the user trigger that generation themselves,
either from the DAW's own user-data folders (auto-discovery) or from an
arbitrary file they exported and saved elsewhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

from studio_pro_mcp.keyscheme import (
    KeySchemeError,
    default_config_path,
    discover_keyscheme,
    parse_keyscheme,
)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def _keyscheme_tools() -> list[Tool]:
    return [
        Tool(
            name="studio_one_generate_command_catalog",
            description=(
                "Generate the full command catalog (built-in commands + this user's own "
                "macros, with readable names) from a Studio Pro / Studio One .keyscheme "
                "export. Every user has different macros installed, so this must be run "
                "per-installation — it is not a static list. By default it auto-discovers "
                "the newest .keyscheme under the DAW's own user-data folders. Pass 'path' "
                "to use a specific file instead — e.g. one exported on another machine, or "
                "saved somewhere outside the DAW's folders. Export a .keyscheme from the "
                "DAW via Preferences -> Keyboard Shortcuts -> Export."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path to a .keyscheme file. Omit to auto-discover the newest "
                            "one under the DAW's user-data folders."
                        ),
                    },
                    "output": {
                        "type": "string",
                        "description": (
                            "Where to write the generated catalog. Defaults to "
                            "~/.studio_pro_mcp/shortcuts.json (or $STUDIO_PRO_MCP_SHORTCUTS)."
                        ),
                    },
                },
                "required": [],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def _dispatch(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "studio_one_generate_command_catalog":
        return _generate_catalog(arguments)
    raise ValueError(f"Unknown keyscheme tool: {name!r}")


def _generate_catalog(arguments: dict[str, Any]) -> list[TextContent]:
    path_arg: str | None = arguments.get("path") or None
    output_arg: str | None = arguments.get("output") or None

    if path_arg:
        source = Path(path_arg)
        if not source.is_file():
            return [TextContent(type="text", text=f"ERROR: no such file: {source}")]
    else:
        discovered = discover_keyscheme()
        if discovered is None:
            return [
                TextContent(
                    type="text",
                    text=(
                        "ERROR: no .keyscheme file found under the DAW's user-data folders. "
                        "Export one from the DAW (Preferences -> Keyboard Shortcuts -> Export) "
                        "and pass its path as 'path'."
                    ),
                )
            ]
        source = discovered

    try:
        data = parse_keyscheme(source)
    except KeySchemeError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]

    destination = Path(output_arg) if output_arg else default_config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)

    text = (
        f"OK: catalog written to {destination}\n\n"
        f"Source:  {source}\n"
        f"Commands: {data['command_count']} scanned, {len(data['shortcuts'])} with a shortcut, "
        f"{data['macro_count']} macro(s) decoded"
    )
    if data["problems"]:
        text += f"\nSkipped: {len(data['problems'])} shortcut(s) could not be translated"
    return [TextContent(type="text", text=text)]
