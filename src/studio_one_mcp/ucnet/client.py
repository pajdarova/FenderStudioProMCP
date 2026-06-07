"""High-level async UCNET client.

Wraps UCNETSession with:
- Handshake and subscription on connect
- A live parameter state cache (updated from incoming events)
- Typed set_parameter / get_parameter API
- An async event stream for callers that want raw updates
- Background reconnection loop

Example usage::

    client = UCNETClient("192.168.1.100")
    await client.connect()

    tempo = await client.get_parameter("/transport/tempo")
    await client.set_parameter("/mixer/channel[0]/fader", 0.75)

    async for update in client.events():
        print(update.path, update.value)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from studio_one_mcp import __version__
from studio_one_mcp.ucnet.protocol import (
    Frame,
    MessageType,
    ParameterUpdate,
    ParameterValue,
    decode_parameter_update,
    encode_hello,
    encode_set_parameter,
    encode_subscribe,
)
from studio_one_mcp.ucnet.session import SessionError, UCNETSession, connect_with_retry

log = logging.getLogger(__name__)

_CLIENT_NAME = "StudioOneMCP"
_DEFAULT_SUBSCRIPTIONS = ["/transport", "/mixer"]


class UCNETError(Exception):
    """Raised when a UCNET operation fails."""


class UCNETClient:
    """High-level UCNET client with parameter state cache.

    Parameters
    ----------
    host:
        IP address or hostname of the Studio One machine.
    port:
        UCNET TCP port (default 52327).
    subscriptions:
        Parameter tree paths to subscribe to on connect.
    """

    def __init__(
        self,
        host: str,
        port: int = 52327,
        subscriptions: list[str] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._subscriptions = subscriptions or _DEFAULT_SUBSCRIPTIONS
        self._session: UCNETSession | None = None
        self._state: dict[str, ParameterValue] = {}
        self._event_queue: asyncio.Queue[ParameterUpdate] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Studio One, handshake, and subscribe to default paths."""
        try:
            self._session = await connect_with_retry(self._host, self._port)
        except SessionError as exc:
            raise UCNETError(str(exc)) from exc

        await self._handshake()
        for path in self._subscriptions:
            await self._subscribe(path)

        self._reader_task = asyncio.create_task(self._read_loop(), name="ucnet-reader")
        log.info("UCNETClient connected and subscribed to %s", self._subscriptions)

    async def close(self) -> None:
        """Disconnect and stop background tasks."""
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> UCNETClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Parameter API
    # ------------------------------------------------------------------

    async def set_parameter(self, path: str, value: ParameterValue) -> None:
        """Write a parameter value to Studio One."""
        if self._session is None:
            raise UCNETError("Client is not connected")
        try:
            await self._session.write(encode_set_parameter(path, value))
            self._state[path] = value
        except SessionError as exc:
            raise UCNETError(f"Failed to set {path!r}: {exc}") from exc

    def get_parameter(self, path: str) -> ParameterValue | None:
        """Return the last-known value for *path* from the cache, or None."""
        return self._state.get(path)

    def get_state_snapshot(self) -> dict[str, ParameterValue]:
        """Return a shallow copy of the full cached state."""
        return dict(self._state)

    # ------------------------------------------------------------------
    # Event stream
    # ------------------------------------------------------------------

    async def events(self) -> AsyncIterator[ParameterUpdate]:
        """Yield parameter updates as they arrive from Studio One."""
        while True:
            update = await self._event_queue.get()
            yield update

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _handshake(self) -> None:
        assert self._session is not None
        await self._session.write(encode_hello(_CLIENT_NAME, __version__))

    async def _subscribe(self, path: str) -> None:
        assert self._session is not None
        await self._session.write(encode_subscribe(path))

    async def _read_loop(self) -> None:
        assert self._session is not None
        async for frame in self._session.frames():
            self._handle_frame(frame)

    def _handle_frame(self, frame: Frame) -> None:
        if frame.msg_type not in (
            MessageType.PARAM_FLOAT,
            MessageType.PARAM_INT,
            MessageType.PARAM_STRING,
            MessageType.SNAPSHOT,
        ):
            log.debug("Ignoring frame type %r", frame.msg_type)
            return

        try:
            if frame.msg_type == MessageType.SNAPSHOT:
                # Snapshot frames bundle multiple parameter updates — treat each
                # sub-frame individually. Sub-frame format is the same as a normal
                # parameter update frame embedded in the snapshot payload.
                self._handle_snapshot(frame.payload)
            else:
                update = decode_parameter_update(frame)
                self._state[update.path] = update.value
                self._event_queue.put_nowait(update)
        except Exception as exc:
            log.warning("Failed to decode frame %r: %s", frame.msg_type, exc)

    def _handle_snapshot(self, payload: bytes) -> None:
        """Parse a snapshot payload: a sequence of embedded parameter frames."""
        import struct

        offset = 0
        while offset + 6 <= len(payload):
            chunk_len = struct.unpack_from("<I", payload, offset)[0]
            msg_type_raw = struct.unpack_from("<H", payload, offset + 4)[0]
            body_start = offset + 6
            body_end = offset + 4 + chunk_len  # chunk_len covers msg_type + payload
            body = payload[body_start:body_end]
            offset = body_end

            try:
                msg_type = MessageType(msg_type_raw)
            except ValueError:
                continue

            if msg_type in (MessageType.PARAM_FLOAT, MessageType.PARAM_INT, MessageType.PARAM_STRING):
                frame = Frame(msg_type=msg_type, payload=body)
                try:
                    update = decode_parameter_update(frame)
                    self._state[update.path] = update.value
                    self._event_queue.put_nowait(update)
                except Exception as exc:
                    log.debug("Skipping malformed snapshot entry: %s", exc)
