"""Entry point for the Studio Pro MCP server."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import Any

import click
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.context import ServerRequestContext

from studio_pro_mcp import __version__
from studio_pro_mcp.midi_bridge import MidiBridge, MidiBridgeError

log = logging.getLogger(__name__)


def _build_server(bridge: MidiBridge, automation: bool = True) -> Server[None]:
    """Construct and configure the MCP server with all tools registered."""
    from studio_pro_mcp.tools.automation import _automation_tools
    from studio_pro_mcp.tools.automation import _dispatch as _automation_dispatch
    from studio_pro_mcp.tools.commands import _command_tools
    from studio_pro_mcp.tools.commands import _dispatch as _command_dispatch
    from studio_pro_mcp.tools.keyscheme_tools import _dispatch as _keyscheme_dispatch
    from studio_pro_mcp.tools.keyscheme_tools import _keyscheme_tools
    from studio_pro_mcp.tools.macro_tools import _dispatch as _macro_dispatch
    from studio_pro_mcp.tools.macro_tools import _macro_tools
    from studio_pro_mcp.tools.mixer import _dispatch as _mixer_dispatch
    from studio_pro_mcp.tools.mixer import _mixer_tools
    from studio_pro_mcp.tools.transport import _dispatch as _transport_dispatch
    from studio_pro_mcp.tools.transport import _transport_tools

    transport_names = {t.name for t in _transport_tools()}
    auto_names = {t.name for t in _automation_tools()} if automation else set()
    macro_names = {t.name for t in _macro_tools()}
    command_names = {t.name for t in _command_tools()}
    keyscheme_names = {t.name for t in _keyscheme_tools()}

    async def _on_list_tools(
        _ctx: ServerRequestContext[None],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        tools = (
            _transport_tools()
            + _mixer_tools()
            + _macro_tools()
            + _command_tools()
            + _keyscheme_tools()
        )
        if automation:
            tools += _automation_tools()
        return types.ListToolsResult(tools=tools)

    async def _on_call_tool(
        _ctx: ServerRequestContext[None],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        name = params.name
        arguments: dict[str, Any] = params.arguments or {}
        content: Sequence[types.ContentBlock]
        try:
            if name in transport_names:
                content = await _transport_dispatch(name, arguments, bridge)
            elif name in auto_names:
                content = await _automation_dispatch(name, arguments)
            elif name in macro_names:
                content = await _macro_dispatch(name, arguments)
            elif name in command_names:
                content = await _command_dispatch(name, arguments)
            elif name in keyscheme_names:
                content = await _keyscheme_dispatch(name, arguments)
            else:
                content = await _mixer_dispatch(name, arguments, bridge)
        except (ValueError, MidiBridgeError) as exc:
            log.error("Tool %r failed: %s", name, exc)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"ERROR: {exc}")],
                is_error=True,
            )
        return types.CallToolResult(content=list(content))

    return Server(
        "studio-pro-mcp",
        version=__version__,
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


async def _run_stdio(bridge: MidiBridge, automation: bool = True) -> None:
    server = _build_server(bridge, automation)
    init_opts = server.create_initialization_options()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_opts)


async def _run_http(bridge: MidiBridge, automation: bool, host: str, port: int) -> None:
    import uvicorn

    server = _build_server(bridge, automation)
    app = server.streamable_http_app(host=host)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--port-name",
    default="StudioPro-MCU",
    show_default=True,
    envvar="STUDIO_PRO_MCP_PORT",
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
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    show_default=True,
    help="stdio for MCP clients like Claude Desktop; http to serve a local Streamable HTTP endpoint.",
)
@click.option(
    "--http-host",
    default="127.0.0.1",
    show_default=True,
    help="Host to bind when --transport=http.",
)
@click.option(
    "--http-port",
    default=8765,
    show_default=True,
    type=int,
    help="Port to bind when --transport=http.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging.")
@click.version_option(__version__)
def main(
    port_name: str,
    message_delay: float,
    list_ports: bool,
    no_automation: bool,
    transport: str,
    http_host: str,
    http_port: int,
    debug: bool,
) -> None:
    """Studio Pro MCP Server — MCU MIDI + keyboard automation + macro generation."""
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
    if transport == "http":
        mode += f" + HTTP on http://{http_host}:{http_port}/mcp"
    click.echo(f"Studio Pro MCP server v{__version__} — {mode}", err=True)

    try:
        if transport == "http":
            asyncio.run(_run_http(bridge, not no_automation, http_host, http_port))
        else:
            asyncio.run(_run_stdio(bridge, not no_automation))
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
        click.echo("Server stopped.", err=True)


if __name__ == "__main__":
    main()
