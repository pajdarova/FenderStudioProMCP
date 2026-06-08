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
from studio_one_mcp.ucnet.client import UCNETClient

log = logging.getLogger(__name__)


def _build_server(
    bridge: MidiBridge,
    ucnet: UCNETClient | None = None,
    automation: bool = True,
) -> Server:
    """Construct and configure the MCP server with all tools registered.

    Parameters
    ----------
    bridge:
        Open MCU MIDI bridge (always required — handles transport + mixer).
    ucnet:
        Optional connected UCNET client. When provided, additional state-query
        and precise parameter-write tools are registered alongside the MCU ones.
    automation:
        When True (default), register OS-level keyboard automation tools.
        Disable with --no-automation if running the server on a different
        machine than Studio One.
    """
    server = Server("studio-one-mcp")

    from studio_one_mcp.tools.automation import _automation_tools
    from studio_one_mcp.tools.automation import _dispatch as _automation_dispatch
    from studio_one_mcp.tools.mixer import _dispatch as _mixer_dispatch
    from studio_one_mcp.tools.mixer import _mixer_tools
    from studio_one_mcp.tools.transport import _dispatch as _transport_dispatch
    from studio_one_mcp.tools.transport import _transport_tools
    from studio_one_mcp.tools.ucnet_state import _dispatch as _ucnet_dispatch
    from studio_one_mcp.tools.ucnet_state import _ucnet_tools

    transport_names = {t.name for t in _transport_tools()}
    ucnet_names = {t.name for t in _ucnet_tools()} if ucnet else set()
    auto_names = {t.name for t in _automation_tools()} if automation else set()

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def handle_list_tools() -> list[types.Tool]:
        tools = _transport_tools() + _mixer_tools()
        if ucnet:
            tools += _ucnet_tools()
        if automation:
            tools += _automation_tools()
        return tools

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            if name in transport_names:
                return await _transport_dispatch(name, arguments, bridge)
            if name in ucnet_names and ucnet is not None:
                return await _ucnet_dispatch(name, arguments, ucnet)
            if name in auto_names:
                return await _automation_dispatch(name, arguments)
            return await _mixer_dispatch(name, arguments, bridge)
        except (ValueError, MidiBridgeError) as exc:
            log.error("Tool %r failed: %s", name, exc)
            return [types.TextContent(type="text", text=f"ERROR: {exc}")]

    return server


async def _run_stdio(bridge: MidiBridge, ucnet: UCNETClient | None, automation: bool = True) -> None:
    server = _build_server(bridge, ucnet, automation)
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
    "--ucnet-host",
    default=None,
    envvar="STUDIO_ONE_UCNET_HOST",
    help="IP address of the Studio One machine for UCNET (Phase 2). "
         "When provided, state-query tools are enabled alongside MCU tools.",
)
@click.option(
    "--ucnet-port",
    default=52327,
    show_default=True,
    type=int,
    envvar="STUDIO_ONE_UCNET_PORT",
    help="UCNET TCP port.",
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
    ucnet_host: str | None,
    ucnet_port: int,
    list_ports: bool,
    no_automation: bool,
    debug: bool,
) -> None:
    """Studio One MCP Server — MCU MIDI bridge (Phase 1) + UCNET (Phase 2).

    Always opens a virtual MIDI port for MCU transport and mixer control.
    Pass --ucnet-host to also connect via UCNET for real state readback.
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

    mode = f"MCU MIDI (port='{port_name}')"
    if ucnet_host:
        mode += f" + UCNET ({ucnet_host}:{ucnet_port})"
    if not no_automation:
        mode += " + automation"
    click.echo(f"Studio One MCP server v{__version__} — {mode}", err=True)

    try:
        asyncio.run(_async_main(bridge, ucnet_host, ucnet_port, not no_automation))
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
        click.echo("Server stopped.", err=True)


async def _async_main(
    bridge: MidiBridge,
    ucnet_host: str | None,
    ucnet_port: int,
    automation: bool,
) -> None:
    ucnet: UCNETClient | None = None
    if ucnet_host:
        ucnet = UCNETClient(ucnet_host, ucnet_port)
        try:
            await ucnet.connect()
            log.info("UCNET connected to %s:%d", ucnet_host, ucnet_port)
        except Exception as exc:
            log.warning("UCNET connection failed (%s) — continuing with MCU only", exc)
            ucnet = None

    try:
        await _run_stdio(bridge, ucnet, automation)
    finally:
        if ucnet:
            await ucnet.close()


if __name__ == "__main__":
    main()
