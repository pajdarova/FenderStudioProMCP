"""Tests for UCNETSession frame I/O using mock asyncio streams."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from studio_one_mcp.ucnet.protocol import (
    MessageType,
    encode_keepalive,
    encode_param_float,
    encode_param_int,
    encode_subscribe,
)
from studio_one_mcp.ucnet.session import SessionError, UCNETSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_streams(data: bytes):
    """Return (reader, writer) mocks where reader yields *data* then EOF."""
    reader = AsyncMock()
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()

    # readexactly returns successive chunks of data
    chunks = []
    offset = 0
    while offset < len(data):
        # Frame header: 6 bytes
        header_end = offset + 6
        if header_end > len(data):
            break
        header = data[offset:header_end]
        payload_length = struct.unpack_from("<I", header, 0)[0]
        body_length = payload_length - 2
        body_end = header_end + body_length
        body = data[header_end:body_end]
        chunks.append(header)
        if body_length > 0:
            chunks.append(body)
        offset = body_end

    # After all data is consumed, raise IncompleteReadError to signal EOF
    chunks.append(Exception("EOF"))  # sentinel

    call_count = [0]

    async def readexactly(n: int):
        idx = call_count[0]
        call_count[0] += 1
        if idx >= len(chunks):
            raise EOFError
        val = chunks[idx]
        if isinstance(val, Exception):
            from asyncio import IncompleteReadError
            raise IncompleteReadError(b"", n)
        return val

    reader.readexactly = readexactly
    return reader, writer


# ---------------------------------------------------------------------------
# Session write
# ---------------------------------------------------------------------------

class TestSessionWrite:
    @pytest.mark.asyncio
    async def test_write_sends_bytes_to_writer(self):
        session = UCNETSession("127.0.0.1")
        reader, writer = _make_mock_streams(b"")
        session._reader = reader
        session._writer = writer

        data = encode_subscribe("/transport")
        await session.write(data)
        writer.write.assert_called_once_with(data)
        writer.drain.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_without_connection_raises(self):
        session = UCNETSession("127.0.0.1")
        with pytest.raises(SessionError, match="not connected"):
            await session.write(b"\x00")


# ---------------------------------------------------------------------------
# Session read_frame
# ---------------------------------------------------------------------------

class TestReadFrame:
    @pytest.mark.asyncio
    async def test_read_param_float_frame(self):
        raw = encode_param_float("/transport/tempo", 120.0)
        reader, writer = _make_mock_streams(raw)
        session = UCNETSession("127.0.0.1")
        session._reader = reader
        session._writer = writer

        frame = await session.read_frame()
        assert frame.msg_type == MessageType.PARAM_FLOAT
        assert len(frame.payload) > 0

    @pytest.mark.asyncio
    async def test_read_keepalive_frame(self):
        raw = encode_keepalive()
        reader, writer = _make_mock_streams(raw)
        session = UCNETSession("127.0.0.1")
        session._reader = reader
        session._writer = writer

        frame = await session.read_frame()
        assert frame.msg_type == MessageType.KEEPALIVE
        assert frame.payload == b""

    @pytest.mark.asyncio
    async def test_read_without_connection_raises(self):
        session = UCNETSession("127.0.0.1")
        with pytest.raises(SessionError, match="not connected"):
            await session.read_frame()


# ---------------------------------------------------------------------------
# frames() async generator — filters keepalives, stops on EOF
# ---------------------------------------------------------------------------

class TestFramesGenerator:
    @pytest.mark.asyncio
    async def test_frames_yields_non_keepalive_frames(self):
        raw = (
            encode_param_float("/transport/tempo", 130.0)
            + encode_keepalive()
            + encode_param_int("/transport/isPlaying", 1)
        )
        reader, writer = _make_mock_streams(raw)
        session = UCNETSession("127.0.0.1")
        session._reader = reader
        session._writer = writer

        frames = []
        async for frame in session.frames():
            frames.append(frame)

        assert len(frames) == 2
        assert frames[0].msg_type == MessageType.PARAM_FLOAT
        assert frames[1].msg_type == MessageType.PARAM_INT

    @pytest.mark.asyncio
    async def test_frames_skips_keepalive(self):
        raw = encode_keepalive() + encode_keepalive()
        reader, writer = _make_mock_streams(raw)
        session = UCNETSession("127.0.0.1")
        session._reader = reader
        session._writer = writer

        frames = []
        async for frame in session.frames():
            frames.append(frame)

        assert frames == []

    @pytest.mark.asyncio
    async def test_frames_stops_on_eof(self):
        raw = encode_param_float("/x", 1.0)
        reader, writer = _make_mock_streams(raw)
        session = UCNETSession("127.0.0.1")
        session._reader = reader
        session._writer = writer

        collected = []
        async for frame in session.frames():
            collected.append(frame)
        # Should complete without hanging
        assert len(collected) == 1


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

class TestConnectErrors:
    @pytest.mark.asyncio
    async def test_connect_failure_raises_session_error(self):
        session = UCNETSession("192.0.2.1", port=9)
        with patch("studio_one_mcp.ucnet.session.asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_conn.side_effect = OSError("refused")
            with pytest.raises(SessionError, match="Cannot connect"):
                await session.connect()

    @pytest.mark.asyncio
    async def test_connect_timeout_raises_session_error(self):
        import asyncio
        session = UCNETSession("192.0.2.1", port=9)
        with patch("studio_one_mcp.ucnet.session.asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_conn.side_effect = asyncio.TimeoutError()
            with pytest.raises(SessionError, match="Cannot connect"):
                await session.connect()
