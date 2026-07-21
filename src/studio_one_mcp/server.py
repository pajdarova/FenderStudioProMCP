"""Entry point for the Studio One MCP server."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

import click
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from studio_one_mcp import __version__
from studio_one_mcp.midi_bridge import MidiBridge, MidiBridgeError

log = logging.getLogger(__name__)


def _build_server(bridge: MidiBridge, automation: bool = True) -> Server:
    """Construct and configure the MCP server with all tools registered."""
    server = Server("studio-one-mcp")

    from studio_one_mcp.tools.automation import _automation_tools
    from studio_one_mcp.tools.automation import _dispatch as _automation_dispatch
    from studio_one_mcp.tools.commands import _command_tools
    from studio_one_mcp.tools.commands import _dispatch as _command_dispatch
    from studio_one_mcp.tools.macro_tools import _dispatch as _macro_dispatch
    from studio_one_mcp.tools.macro_tools import _macro_tools
    from studio_one_mcp.tools.mixer import _dispatch as _mixer_dispatch
    from studio_one_mcp.tools.mixer import _mixer_tools
    from studio_one_mcp.tools.transport import _dispatch as _transport_dispatch
    from studio_one_mcp.tools.transport import _transport_tools

    transport_names = {t.name for t in _transport_tools()}
    auto_names = {t.name for t in _automation_tools()} if automation else set()
    macro_names = {t.name for t in _macro_tools()}
    command_names = {t.name for t in _command_tools()}

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def handle_list_tools() -> list[types.Tool]:
        tools = _transport_tools() + _mixer_tools() + _macro_tools() + _command_tools()
        if automation:
            tools += _automation_tools()
        return tools

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            if name in transport_names:
                return await _transport_dispatch(name, arguments, bridge)
            if name in auto_names:
                return await _automation_dispatch(name, arguments)
            if name in macro_names:
                return await _macro_dispatch(name, arguments)
            if name in command_names:
                return await _command_dispatch(name, arguments, bridge)
            return await _mixer_dispatch(name, arguments, bridge)
        except (ValueError, MidiBridgeError) as exc:
            log.error("Tool %r failed: %s", name, exc)
            return [types.TextContent(type="text", text=f"ERROR: {exc}")]

    return server


async def _run_stdio(bridge: MidiBridge, automation: bool = True) -> None:
    server = _build_server(bridge, automation)
    init_opts = InitializationOptions(
        server_name="studio-one-mcp",
        server_version=__version__,
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_opts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--port-name",
    default="StudioOneMCP",
    show_default=True,
    envvar="STUDIO_ONE_MCP_PORT",
    help="Name of the virtual MIDI output port to create.",
)
@click.option(
    "--message-delay",
    default=0.02,
    show_default=True,
    type=float,
    help="Seconds to wait between MIDI note-on and note-off (press/release).",
)
@click.option(
    "--list-ports", is_flag=True,
    help="List available MIDI output ports and exit.",
)
@click.option(
    "--no-automation",
    is_flag=True,
    help="Disable OS-level keyboard automation tools (use when server runs remotely).",
)
@click.option("--debug", is_flag=True, help="Enable debug logging.")
@click.version_option(__version__)
def main(
    port_name: str,
    message_delay: float,
    list_ports: bool,
    no_automation: bool,
    debug: bool,
) -> None:
    """Studio One MCP Server — MCU MIDI + keyboard automation + macro generation."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if list_ports:
        ports = MidiBridge.list_available_ports()
        if ports:
            click.echo("Available MIDI output ports:")
            for i, name in enumerate(ports):
                click.echo(f"  {i}: {name}")
        else:
            click.echo("No MIDI output ports found.")
        return

    bridge = MidiBridge(port_name=port_name, message_delay=message_delay)
    try:
        bridge.open()
    except MidiBridgeError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    mode = f"MCU MIDI (port='{port_name}')"
    if not no_automation:
        mode += " + automation"
    click.echo(f"Studio One MCP server v{__version__} — {mode}", err=True)

    try:
        asyncio.run(_run_stdio(bridge, not no_automation))
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
        click.echo("Server stopped.", err=True)


if __name__ == "__main__":
    main()
