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


def _build_server(bridge: MidiBridge) -> Server:
    """Construct and configure the MCP server with all tools registered."""
    server = Server("studio-one-mcp")

    # Collect tools from both modules
    from studio_one_mcp.tools.mixer import _dispatch as _mixer_dispatch
    from studio_one_mcp.tools.mixer import _mixer_tools
    from studio_one_mcp.tools.transport import _dispatch as _transport_dispatch
    from studio_one_mcp.tools.transport import _transport_tools

    all_transport_names = {t.name for t in _transport_tools()}

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def handle_list_tools() -> list[types.Tool]:
        return _transport_tools() + _mixer_tools()

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            if name in all_transport_names:
                return await _transport_dispatch(name, arguments, bridge)
            else:
                return await _mixer_dispatch(name, arguments, bridge)
        except (ValueError, MidiBridgeError) as exc:
            log.error("Tool %r failed: %s", name, exc)
            return [types.TextContent(type="text", text=f"ERROR: {exc}")]

    return server


async def _run_stdio(bridge: MidiBridge) -> None:
    server = _build_server(bridge)
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
    "--transport",
    default="stdio",
    show_default=True,
    type=click.Choice(["stdio"], case_sensitive=False),
    help="MCP transport to use. Only 'stdio' is supported in Phase 1.",
)
@click.option("--list-ports", is_flag=True, help="List available MIDI output ports and exit.")
@click.option("--debug", is_flag=True, help="Enable debug logging.")
@click.version_option(__version__)
def main(
    port_name: str,
    message_delay: float,
    transport: str,
    list_ports: bool,
    debug: bool,
) -> None:
    """Studio One MCP Server — MCU MIDI bridge (Phase 1).

    Exposes Studio One transport and mixer controls as MCP tools, communicating
    via the Mackie Control Universal protocol over a virtual MIDI port.
    """
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

    click.echo(f"Studio One MCP server v{__version__} starting on port '{port_name}' …", err=True)

    try:
        asyncio.run(_run_stdio(bridge))
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
        click.echo("Server stopped.", err=True)


if __name__ == "__main__":
    main()
