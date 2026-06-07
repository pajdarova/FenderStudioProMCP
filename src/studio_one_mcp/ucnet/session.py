"""Asyncio TCP session for UCNET: frame reader/writer with keepalive.

Responsible for:
- Opening and maintaining the TCP connection to Studio One
- Reading length-prefixed frames from the stream
- Writing frames to the stream
- Sending periodic keepalives so Studio One doesn't drop the connection
- Reconnecting on connection loss (with exponential back-off)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from studio_one_mcp.ucnet.protocol import (
    FRAME_HEADER_SIZE,
    Frame,
    decode_frame_header,
    encode_keepalive,
)

log = logging.getLogger(__name__)

_DEFAULT_PORT = 52327
_KEEPALIVE_INTERVAL = 5.0   # seconds
_CONNECT_TIMEOUT = 10.0     # seconds
_BACKOFF_BASE = 1.0         # seconds
_BACKOFF_MAX = 30.0         # seconds


class SessionError(Exception):
    """Raised when the TCP session cannot be established or is lost."""


class UCNETSession:
    """Low-level TCP session: reads/writes raw UCNET frames.

    Usage::

        async with UCNETSession("127.0.0.1") as session:
            await session.write(encode_hello("my-client", "1.0"))
            async for frame in session.frames():
                ...

    Parameters
    ----------
    host:
        Hostname or IP address of the Studio One machine.
    port:
        TCP port (default 52327).
    keepalive_interval:
        How often to send a keepalive frame (seconds).
    """

    def __init__(
        self,
        host: str,
        port: int = _DEFAULT_PORT,
        keepalive_interval: float = _KEEPALIVE_INTERVAL,
    ) -> None:
        self._host = host
        self._port = port
        self._keepalive_interval = keepalive_interval
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._keepalive_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the TCP connection. Raises SessionError on failure."""
        log.info("Connecting to UCNET at %s:%d …", self._host, self._port)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=_CONNECT_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise SessionError(f"Cannot connect to {self._host}:{self._port}: {exc}") from exc

        log.info("UCNET TCP connection established")
        self._keepalive_task = asyncio.create_task(self._keepalive_loop(), name="ucnet-keepalive")

    async def close(self) -> None:
        """Close the TCP connection gracefully."""
        if self._keepalive_task:
            self._keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._keepalive_task
            self._keepalive_task = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._writer = None
            self._reader = None
        log.info("UCNET session closed")

    async def __aenter__(self) -> UCNETSession:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    async def write(self, data: bytes) -> None:
        """Send raw frame bytes to Studio One."""
        if self._writer is None:
            raise SessionError("Session is not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def read_frame(self) -> Frame:
        """Read and return exactly one UCNET frame from the stream."""
        if self._reader is None:
            raise SessionError("Session is not connected")

        header_bytes = await self._reader.readexactly(FRAME_HEADER_SIZE)
        payload_length, msg_type = decode_frame_header(header_bytes)

        body_length = payload_length - 2  # subtract the msg_type field already read
        payload = await self._reader.readexactly(body_length) if body_length > 0 else b""

        return Frame(msg_type=msg_type, payload=payload)

    async def frames(self) -> AsyncIterator[Frame]:
        """Yield UCNET frames as they arrive. Stops on connection close."""
        while True:
            try:
                frame = await self.read_frame()
                if not frame.is_keepalive:
                    yield frame
            except asyncio.IncompleteReadError:
                log.warning("UCNET connection closed by remote")
                break
            except SessionError:
                break

    # ------------------------------------------------------------------
    # Keepalive loop
    # ------------------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        ping = encode_keepalive()
        while True:
            await asyncio.sleep(self._keepalive_interval)
            try:
                await self.write(ping)
                log.debug("UCNET keepalive sent")
            except SessionError:
                log.warning("Keepalive failed — connection lost")
                break


def _backoff(attempt: int) -> float:
    return float(min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX))


async def connect_with_retry(
    host: str,
    port: int = _DEFAULT_PORT,
    max_attempts: int = 5,
) -> UCNETSession:
    """Try to connect, retrying with exponential back-off on failure."""
    for attempt in range(max_attempts):
        session = UCNETSession(host, port)
        try:
            await session.connect()
            return session
        except SessionError as exc:
            wait = _backoff(attempt)
            log.warning("%s — retrying in %.1fs (attempt %d/%d)", exc, wait, attempt + 1, max_attempts)
            await asyncio.sleep(wait)

    raise SessionError(f"Failed to connect to {host}:{port} after {max_attempts} attempts")
