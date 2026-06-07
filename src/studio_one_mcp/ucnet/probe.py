"""UCNET parameter probe — discovers real parameter paths from a live Studio One instance.

Usage::

    # Auto-discover Studio One on the LAN, then record for 30 s
    studio-one-ucnet-probe

    # Connect directly to a known host
    studio-one-ucnet-probe --host 192.168.1.100 --duration 60

    # Save results to a file
    studio-one-ucnet-probe --host 192.168.1.100 --output paths.json

The tool subscribes to the root path "/" and records every ParameterUpdate
that arrives from Studio One.  Output JSON maps each parameter path to its
last-seen value and type, which can then be used to update the speculative
path constants in tools/ucnet_state.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from collections import defaultdict
from typing import Any

import click

from studio_one_mcp.ucnet.client import UCNETClient, UCNETError
from studio_one_mcp.ucnet.discovery import discover_hosts
from studio_one_mcp.ucnet.protocol import MessageType

log = logging.getLogger(__name__)

_DEFAULT_DURATION = 30
_DEFAULT_PORT = 52327


# ---------------------------------------------------------------------------
# Core probe logic
# ---------------------------------------------------------------------------

async def _probe(
    host: str,
    port: int,
    duration: float,
    output: str | None,
    verbose: bool,
) -> int:
    """Connect, record, report. Returns 0 on success, 1 on error."""
    click.echo(f"Connecting to {host}:{port} …")

    client = UCNETClient(host, port, subscriptions=["/"])
    try:
        await client.connect()
    except UCNETError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        return 1

    click.echo(f"Connected. Recording parameter updates for {duration:.0f} s …")
    click.echo("(Interact with Studio One now — move faders, toggle mute, change tempo, etc.)")

    seen: dict[str, dict[str, Any]] = {}
    type_map = {
        MessageType.PARAM_FLOAT: "float",
        MessageType.PARAM_INT: "int",
        MessageType.PARAM_STRING: "string",
    }
    update_count: dict[str, int] = defaultdict(int)

    deadline = time.monotonic() + duration

    async def _collect() -> None:
        async for update in client.events():
            now = time.monotonic()
            if now >= deadline:
                break
            seen[update.path] = {
                "type": type_map.get(update.msg_type, "unknown"),
                "last_value": update.value,
                "last_seen": round(now, 3),
            }
            update_count[update.path] += 1
            if verbose:
                click.echo(f"  {update.path} = {update.value!r}  ({update.msg_type.name})")

    try:
        await asyncio.wait_for(_collect(), timeout=duration + 1)
    except asyncio.TimeoutError:
        pass
    finally:
        await client.close()

    # Annotate with update counts
    for path, info in seen.items():
        info["update_count"] = update_count[path]

    total = sum(update_count.values())
    click.echo(f"\nRecorded {total} updates across {len(seen)} unique paths.")

    report = {
        "host": host,
        "port": port,
        "duration_s": duration,
        "total_updates": total,
        "paths": dict(sorted(seen.items())),
    }

    json_out = json.dumps(report, indent=2, default=str)

    if output:
        with open(output, "w") as f:
            f.write(json_out)
        click.echo(f"Report written to: {output}")
    else:
        click.echo("\n" + json_out)

    return 0


async def _discover_and_probe(
    port: int,
    duration: float,
    output: str | None,
    verbose: bool,
) -> int:
    click.echo("Discovering Studio One on the local network (3 s) …")
    hosts = await discover_hosts(timeout=3.0)
    if not hosts:
        click.echo("No UCNET hosts found. Try --host to specify an address directly.", err=True)
        return 1

    click.echo(f"Found {len(hosts)} host(s):")
    for i, h in enumerate(hosts):
        click.echo(f"  [{i}] {h}")

    chosen = hosts[0]
    if len(hosts) > 1:
        click.echo(f"Using first host: {chosen}")

    return await _probe(chosen.ip, chosen.tcp_port, duration, output, verbose)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command("studio-one-ucnet-probe")
@click.option(
    "--host", default=None,
    help="IP address of the Studio One machine. If omitted, UDP discovery is used.",
)
@click.option(
    "--port", default=_DEFAULT_PORT, show_default=True, type=int,
    help="UCNET TCP port.",
)
@click.option(
    "--duration", default=_DEFAULT_DURATION, show_default=True, type=float,
    help="How many seconds to listen for parameter updates.",
)
@click.option(
    "--output", default=None, metavar="FILE",
    help="Write JSON report to FILE instead of stdout.",
)
@click.option("--verbose", "-v", is_flag=True, help="Print each update as it arrives.")
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main(
    host: str | None,
    port: int,
    duration: float,
    output: str | None,
    verbose: bool,
    debug: bool,
) -> None:
    """Probe a live Studio One instance and record UCNET parameter paths.

    Useful for mapping out the real parameter tree so the speculative paths
    in tools/ucnet_state.py can be corrected.

    \\b
    Examples:
      studio-one-ucnet-probe --host 192.168.1.5 --duration 60 --output paths.json
      studio-one-ucnet-probe -v   # auto-discover + verbose live output
    """
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if host:
        rc = asyncio.run(_probe(host, port, duration, output, verbose))
    else:
        rc = asyncio.run(_discover_and_probe(port, duration, output, verbose))

    sys.exit(rc)


if __name__ == "__main__":
    main()
