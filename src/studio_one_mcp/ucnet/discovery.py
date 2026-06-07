"""UDP discovery for UCNET hosts on the local network.

Studio One listens on UDP port 54321. Sending the discovery payload as a
broadcast causes it to reply with a JSON blob describing itself.

These details are PRELIMINARY — verified against community packet captures
but not against PreSonus documentation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

_DISCOVERY_PORT = 54321
_DISCOVERY_PAYLOAD = b"ucnet_discover\x00"
_DISCOVERY_TIMEOUT = 3.0  # seconds to wait for responses


@dataclass
class UCNETHost:
    ip: str
    name: str
    version: str
    host_id: str
    tcp_port: int

    def __str__(self) -> str:
        return f"{self.name} ({self.ip}:{self.tcp_port}) v{self.version}"


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.hosts: list[UCNETHost] = []
        self._done: asyncio.Future[None] = asyncio.get_event_loop().create_future()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        transport.sendto(_DISCOVERY_PAYLOAD, ("<broadcast>", _DISCOVERY_PORT))

    def datagram_received(self, data: bytes, addr: tuple[str | int, int]) -> None:
        ip = str(addr[0])
        try:
            info = json.loads(data.decode())
            host = UCNETHost(
                ip=ip,
                name=info.get("name", "Studio One"),
                version=info.get("version", "unknown"),
                host_id=info.get("host_id", ""),
                tcp_port=int(info.get("tcp_port", 52327)),
            )
            log.info("Discovered UCNET host: %s", host)
            self.hosts.append(host)
        except Exception as exc:
            log.debug("Ignoring malformed discovery response from %s: %s", ip, exc)

    def error_received(self, exc: Exception) -> None:
        log.debug("Discovery socket error: %s", exc)


async def discover_hosts(timeout: float = _DISCOVERY_TIMEOUT) -> list[UCNETHost]:
    """Broadcast a discovery probe and collect responding UCNET hosts.

    Parameters
    ----------
    timeout:
        How long to wait for responses before returning (seconds).

    Returns
    -------
    list[UCNETHost]
        Zero or more hosts that responded within *timeout*.
    """
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _DiscoveryProtocol,
        family=__import__("socket").AF_INET,
        allow_broadcast=True,
    )
    try:
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    return protocol.hosts
