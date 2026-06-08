"""MCP tools that dispatch Studio One commands via the Extension IPC bridge."""
from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

from studio_one_mcp.extension_installer import install_extension, is_installed
from studio_one_mcp.ipc_bridge import IPCBridge, IPCError, IPCTimeoutError


def _ipc_tools() -> list[Tool]:
    return [
        Tool(
            name="install_ipc_extension",
            description=(
                "Install the StudioOneMCPBridge JS Extension into Studio One's Extensions "
                "folder. Must be done once per machine. Restart Studio One after install."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "description": "Re-install even if already installed.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="dispatch_command",
            description=(
                "Dispatch any Studio One command directly via the IPC bridge. "
                "Requires the StudioOneMCPBridge extension (run install_ipc_extension first). "
                "Categories: Track, Edit, Audio, Event, Console, Transport, View, Zoom, "
                "Navigation, Macros, Arranger, Devices, Media, Musical Functions, Project, Show, Song."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Command category (e.g. 'Track', 'Edit', 'Audio').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Command name within the category.",
                    },
                    "args": {
                        "type": "object",
                        "description": "Optional command arguments as string key-value pairs.",
                        "additionalProperties": {"type": "string"},
                    },
                    "transaction": {
                        "type": "string",
                        "description": "Wrap in a named undo transaction (optional).",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Seconds to wait for response (default 5).",
                    },
                },
                "required": ["category", "name"],
            },
        ),
        Tool(
            name="create_audio_track",
            description="Add a new mono audio track to the current Song.",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {
                        "type": "number",
                        "description": "Response timeout in seconds (default 5).",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="create_instrument_track",
            description=(
                "Add a new instrument track to the current Song. "
                "Optionally insert a plugin by its class ID GUID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "plugin_cid": {
                        "type": "string",
                        "description": (
                            "Plugin class ID GUID to insert on the new track "
                            "(use auto_list_plugins to look up GUIDs)."
                        ),
                    },
                    "timeout": {"type": "number"},
                },
                "required": [],
            },
        ),
        Tool(
            name="insert_plugin_direct",
            description=(
                "Insert a plugin on the currently selected channel via the IPC bridge. "
                "Faster than auto_generate_insert_macro because it doesn't create a macro file — "
                "the command is sent directly. Use auto_list_plugins to find the plugin GUID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "plugin_cid": {
                        "type": "string",
                        "description": "Plugin class ID GUID.",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Preset name (default 'default').",
                    },
                    "timeout": {"type": "number"},
                },
                "required": ["plugin_cid"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def _dispatch(
    name: str, arguments: dict[str, Any], bridge: IPCBridge
) -> list[TextContent]:
    if name == "install_ipc_extension":
        return _install_extension(arguments)
    if name == "dispatch_command":
        return await _dispatch_command(arguments, bridge)
    if name == "create_audio_track":
        return await _create_audio_track(arguments, bridge)
    if name == "create_instrument_track":
        return await _create_instrument_track(arguments, bridge)
    if name == "insert_plugin_direct":
        return await _insert_plugin_direct(arguments, bridge)
    raise ValueError(f"Unknown IPC tool: {name!r}")


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _install_extension(arguments: dict[str, Any]) -> list[TextContent]:
    force = bool(arguments.get("force", False))
    ok, msg = install_extension(force=force)
    prefix = "OK" if ok else "ERROR"
    installed_note = ""
    if ok and is_installed():
        installed_note = "\nExtension is present in the Extensions folder."
    return [TextContent(type="text", text=f"{prefix}: {msg}{installed_note}")]


async def _dispatch_command(
    arguments: dict[str, Any], bridge: IPCBridge
) -> list[TextContent]:
    category: str = arguments.get("category", "")
    cmd_name: str = arguments.get("name", "")
    args: dict[str, str] | None = arguments.get("args") or None
    transaction: str | None = arguments.get("transaction") or None
    timeout: float = float(arguments.get("timeout", 5.0))

    try:
        resp = await bridge.dispatch(
            category, cmd_name, args=args, transaction=transaction, timeout=timeout
        )
        return [TextContent(type="text", text=f"OK: {category}/{cmd_name} dispatched (id={resp.id})")]
    except IPCTimeoutError as exc:
        return [TextContent(type="text", text=f"TIMEOUT: {exc}")]
    except IPCError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]


async def _create_audio_track(
    arguments: dict[str, Any], bridge: IPCBridge
) -> list[TextContent]:
    timeout = float(arguments.get("timeout", 5.0))
    try:
        await bridge.dispatch("Track", "Add Audio Track (mono)", timeout=timeout)
        return [TextContent(type="text", text="OK: Audio track added.")]
    except IPCTimeoutError as exc:
        return [TextContent(type="text", text=f"TIMEOUT: {exc}")]
    except IPCError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]


async def _create_instrument_track(
    arguments: dict[str, Any], bridge: IPCBridge
) -> list[TextContent]:
    timeout = float(arguments.get("timeout", 5.0))
    plugin_cid: str | None = arguments.get("plugin_cid") or None

    try:
        # Add instrument track (opens dialog in some versions — use with care)
        await bridge.dispatch("Track", "Add Instrument Track", timeout=timeout)

        if plugin_cid:
            await bridge.dispatch(
                "Track",
                "Add Insert to Selected Channels",
                args={"mode": "1", "cid": plugin_cid, "preset": "default"},
                timeout=timeout,
            )
            return [TextContent(type="text", text=f"OK: Instrument track added with plugin {plugin_cid}.")]

        return [TextContent(type="text", text="OK: Instrument track added.")]
    except IPCTimeoutError as exc:
        return [TextContent(type="text", text=f"TIMEOUT: {exc}")]
    except IPCError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]


async def _insert_plugin_direct(
    arguments: dict[str, Any], bridge: IPCBridge
) -> list[TextContent]:
    plugin_cid: str = arguments.get("plugin_cid", "")
    preset: str = arguments.get("preset", "default")
    timeout = float(arguments.get("timeout", 5.0))

    if not plugin_cid:
        return [TextContent(type="text", text="ERROR: plugin_cid is required.")]

    try:
        await bridge.dispatch(
            "Track",
            "Add Insert to Selected Channels",
            args={"mode": "1", "cid": plugin_cid, "preset": preset},
            transaction="Insert plugin",
            timeout=timeout,
        )
        return [TextContent(type="text", text=f"OK: Plugin {plugin_cid} inserted.")]
    except IPCTimeoutError as exc:
        return [TextContent(type="text", text=f"TIMEOUT: {exc}")]
    except IPCError as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}")]
