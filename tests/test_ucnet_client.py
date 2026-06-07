"""Tests for UCNETClient state cache and frame handling (no real TCP required)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from studio_one_mcp.ucnet.client import UCNETClient, UCNETError
from studio_one_mcp.ucnet.protocol import (
    Frame,
    MessageType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_param_float_frame(path: str, value: float) -> Frame:
    import struct

    from studio_one_mcp.ucnet.protocol import _encode_str
    payload = _encode_str(path) + struct.pack("<f", value)
    return Frame(msg_type=MessageType.PARAM_FLOAT, payload=payload)


def _make_param_int_frame(path: str, value: int) -> Frame:
    import struct

    from studio_one_mcp.ucnet.protocol import _encode_str
    payload = _encode_str(path) + struct.pack("<i", value)
    return Frame(msg_type=MessageType.PARAM_INT, payload=payload)


def _make_param_string_frame(path: str, value: str) -> Frame:
    from studio_one_mcp.ucnet.protocol import _encode_str
    payload = _encode_str(path) + _encode_str(value)
    return Frame(msg_type=MessageType.PARAM_STRING, payload=payload)


# ---------------------------------------------------------------------------
# State cache
# ---------------------------------------------------------------------------

class TestStateCacheUpdates:
    def test_float_frame_updates_cache(self):
        client = UCNETClient("127.0.0.1")
        frame = _make_param_float_frame("/transport/tempo", 128.0)
        client._handle_frame(frame)
        value = client.get_parameter("/transport/tempo")
        assert value == pytest.approx(128.0, abs=1e-3)

    def test_int_frame_updates_cache(self):
        client = UCNETClient("127.0.0.1")
        frame = _make_param_int_frame("/transport/isPlaying", 1)
        client._handle_frame(frame)
        assert client.get_parameter("/transport/isPlaying") == 1

    def test_string_frame_updates_cache(self):
        client = UCNETClient("127.0.0.1")
        frame = _make_param_string_frame("/mixer/channel[0]/name", "Kick")
        client._handle_frame(frame)
        assert client.get_parameter("/mixer/channel[0]/name") == "Kick"

    def test_later_update_overwrites_cache(self):
        client = UCNETClient("127.0.0.1")
        client._handle_frame(_make_param_float_frame("/transport/tempo", 120.0))
        client._handle_frame(_make_param_float_frame("/transport/tempo", 140.0))
        assert client.get_parameter("/transport/tempo") == pytest.approx(140.0, abs=1e-3)

    def test_unknown_path_returns_none(self):
        client = UCNETClient("127.0.0.1")
        assert client.get_parameter("/nonexistent/path") is None

    def test_get_state_snapshot_returns_copy(self):
        client = UCNETClient("127.0.0.1")
        client._handle_frame(_make_param_float_frame("/a", 1.0))
        snap = client.get_state_snapshot()
        snap["/a"] = 99.0
        assert client.get_parameter("/a") != 99.0

    def test_keepalive_frame_ignored(self):
        client = UCNETClient("127.0.0.1")
        frame = Frame(msg_type=MessageType.KEEPALIVE, payload=b"")
        client._handle_frame(frame)
        assert client.get_state_snapshot() == {}

    def test_unknown_frame_type_ignored(self):
        client = UCNETClient("127.0.0.1")
        frame = Frame(msg_type=MessageType.HELLO, payload=b"\x00" * 10)
        client._handle_frame(frame)  # should not raise
        assert client.get_state_snapshot() == {}


# ---------------------------------------------------------------------------
# Event queue
# ---------------------------------------------------------------------------

class TestEventQueue:
    def test_float_frame_enqueues_event(self):
        client = UCNETClient("127.0.0.1")
        client._handle_frame(_make_param_float_frame("/transport/tempo", 130.0))
        update = client._event_queue.get_nowait()
        assert update.path == "/transport/tempo"
        assert update.value == pytest.approx(130.0, abs=1e-3)

    def test_multiple_frames_enqueue_in_order(self):
        client = UCNETClient("127.0.0.1")
        client._handle_frame(_make_param_int_frame("/a", 1))
        client._handle_frame(_make_param_int_frame("/b", 2))
        first = client._event_queue.get_nowait()
        second = client._event_queue.get_nowait()
        assert first.path == "/a"
        assert second.path == "/b"


# ---------------------------------------------------------------------------
# Snapshot handling
# ---------------------------------------------------------------------------

class TestSnapshotHandling:
    def _build_snapshot_payload(self, frames: list[Frame]) -> bytes:
        """Pack multiple parameter frames into a snapshot payload."""
        import struct
        result = b""
        for frame in frames:
            payload_length = len(frame.payload) + 2
            result += struct.pack("<IH", payload_length, int(frame.msg_type)) + frame.payload
        return result

    def test_snapshot_populates_multiple_paths(self):
        client = UCNETClient("127.0.0.1")
        inner = [
            _make_param_float_frame("/transport/tempo", 110.0),
            _make_param_int_frame("/transport/isPlaying", 0),
            _make_param_string_frame("/mixer/channel[0]/name", "Bass"),
        ]
        payload = self._build_snapshot_payload(inner)
        snapshot_frame = Frame(msg_type=MessageType.SNAPSHOT, payload=payload)
        client._handle_frame(snapshot_frame)

        assert client.get_parameter("/transport/tempo") == pytest.approx(110.0, abs=1e-3)
        assert client.get_parameter("/transport/isPlaying") == 0
        assert client.get_parameter("/mixer/channel[0]/name") == "Bass"

    def test_snapshot_with_empty_payload_is_harmless(self):
        client = UCNETClient("127.0.0.1")
        frame = Frame(msg_type=MessageType.SNAPSHOT, payload=b"")
        client._handle_frame(frame)  # should not raise


# ---------------------------------------------------------------------------
# set_parameter writes through session
# ---------------------------------------------------------------------------

class TestSetParameter:
    @pytest.mark.asyncio
    async def test_set_parameter_calls_session_write(self):
        client = UCNETClient("127.0.0.1")
        mock_session = AsyncMock()
        client._session = mock_session

        await client.set_parameter("/transport/tempo", 120.0)
        mock_session.write.assert_awaited_once()
        written = mock_session.write.call_args[0][0]
        assert isinstance(written, bytes) and len(written) > 0

    @pytest.mark.asyncio
    async def test_set_parameter_updates_local_cache(self):
        client = UCNETClient("127.0.0.1")
        client._session = AsyncMock()
        await client.set_parameter("/transport/tempo", 120.0)
        assert client.get_parameter("/transport/tempo") == 120.0

    @pytest.mark.asyncio
    async def test_set_parameter_without_session_raises(self):
        client = UCNETClient("127.0.0.1")
        with pytest.raises(UCNETError, match="not connected"):
            await client.set_parameter("/x", 1.0)


# ---------------------------------------------------------------------------
# Malformed frame resilience
# ---------------------------------------------------------------------------

class TestResilience:
    def test_truncated_float_payload_does_not_crash(self):
        client = UCNETClient("127.0.0.1")
        frame = Frame(msg_type=MessageType.PARAM_FLOAT, payload=b"\x04\x00/ab")
        client._handle_frame(frame)  # bad payload — should log and continue

    def test_truncated_string_payload_does_not_crash(self):
        client = UCNETClient("127.0.0.1")
        frame = Frame(msg_type=MessageType.PARAM_STRING, payload=b"\x03\x00foo")
        client._handle_frame(frame)
