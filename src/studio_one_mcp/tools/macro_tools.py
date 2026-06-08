"""MCP tools for Studio One macro generation and plugin enumeration."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from studio_one_mcp.macro_writer import MacroCommand, macro_command_name, write_macro
from studio_one_mcp.plugin_db import PluginNotFoundError, find_plugin, list_plugins

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def _macro_tools() -> list[Tool]:
    return [
        Tool(
            name="auto_list_plugins",
            description=(
                "List all plugins installed in Studio One, grouped by category "
                "(AudioSynth, AudioEffect, MusicEffect). "
                "Pass an optional 'category' to filter results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": (
                            "Optional category filter: AudioSynth, AudioEffect, or MusicEffect."
                        ),
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="auto_generate_insert_macro",
            description=(
                "Look up a plugin by name and generate a Studio One macro file that inserts "
                "it on the selected channel. The macro appears in the Studio One toolbar "
                "under the MCP group. No shortcut required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Plugin name (case-insensitive, partial match supported).",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Preset name to load. Defaults to 'default'.",
                    },
                    "mode": {
                        "type": "integer",
                        "description": "Insert mode (1 = insert on selected channel). Defaults to 1.",
                    },
                },
                "required": ["name"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def _dispatch(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "auto_list_plugins":
        return _list_plugins(arguments)
    if name == "auto_generate_insert_macro":
        return _generate_insert_macro(arguments)
    raise ValueError(f"Unknown macro tool: {name!r}")


def _list_plugins(arguments: dict[str, Any]) -> list[TextContent]:
    category: str | None = arguments.get("category") or None
    plugins = list_plugins(category=category)
    if not plugins:
        msg = "No plugins found in Studio One DataStore.db."
        if category:
            msg = f"No plugins found for category {category!r}."
        return [TextContent(type="text", text=msg)]

    # Group by category, deduplicate by name
    grouped: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for p in plugins:
        key = (p.category, p.name)
        if key in seen:
            continue
        seen.add(key)
        cat = p.category or "Unknown"
        entry = p.name
        if p.vendor:
            entry += f" ({p.vendor})"
        grouped.setdefault(cat, []).append(entry)

    lines: list[str] = []
    for cat in sorted(grouped):
        lines.append(f"\n## {cat}")
        for entry in grouped[cat]:
            lines.append(f"  - {entry}")

    total = sum(len(v) for v in grouped.values())
    header = f"Found {total} plugin(s)"
    if category:
        header += f" in category {category!r}"
    text = header + ":" + "\n".join(lines)
    return [TextContent(type="text", text=text)]


def _generate_insert_macro(arguments: dict[str, Any]) -> list[TextContent]:
    plugin_name: str = arguments.get("name", "")
    preset: str = arguments.get("preset", "default")
    mode: int = int(arguments.get("mode", 1))

    try:
        plugin = find_plugin(plugin_name)
    except PluginNotFoundError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]

    commands = [
        MacroCommand(
            category="Track",
            name="Add Insert to Selected Channels",
            arguments={"mode": str(mode), "cid": plugin.cid, "preset": preset},
        ),
        MacroCommand(
            category="Console",
            name="Show Channel Editor",
        ),
    ]

    title = f"Insert {plugin.name}"
    path = write_macro(title, "MCP", commands)
    cmd_name = macro_command_name(title)

    text = (
        f"OK: Macro written to {path}\n\n"
        f"Plugin: {plugin.name} ({plugin.vendor})\n"
        f"Category: {plugin.category}\n"
        f"GUID: {plugin.cid}\n\n"
        f"Studio One command name: {cmd_name}\n\n"
        "To run this macro in Studio One:\n"
        "  1. Reload macros: Studio One menu → Macros → Reload Macros\n"
        "  2. Select a channel/track in the Console or Song page\n"
        "  3. Open the macro toolbar and find the MCP group\n"
        f"  4. Click '{title}' to insert the plugin\n\n"
        "Or assign a keyboard shortcut via Preferences → Keyboard Shortcuts → Macros."
    )
    return [TextContent(type="text", text=text)]
