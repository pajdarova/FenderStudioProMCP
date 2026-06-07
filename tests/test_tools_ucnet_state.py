"""Tests for UCNET state MCP tool dispatchers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from studio_one_mcp.tools.ucnet_state import _dispatch, _ucnet_tools
from studio_one_mcp.ucnet.client import UCNETClient


@pytest.fixture()
def client():
    """Return a UCNETClient with pre-populated state cache (no real connection)."""
    c = UCNETClient("127.0.0.1")
    # Seed some state directly into the cache
    c._state = {
        "/transport/tempo": 120.0,
        "/transport/isPlaying": 1,
        "/transport/isRecording": 0,
        "/transport/positionBars": "1.1.1.0",
        "/mixer/channel[0]/fader": 0.75,
        "/mixer/channel[0]/mute": 0,
        "/mixer/channel[0]/solo": 0,
        "/mixer/channel[0]/name": "Kick",
        "/mixer/channel[1]/fader": 0.5,
        "/mixer/channel[1]/mute": 1,
        "/mixer/channel[1]/name": "Snare",
    }
    return c


class TestToolList:
    def test_returns_five_tools(self):
        assert len(_ucnet_tools()) == 5

    def test_tool_names(self):
        names = {t.name for t in _ucnet_tools()}
        assert names == {
            "ucnet_get_transport_state",
            "ucnet_get_channel_state",
            "ucnet_set_fader",
            "ucnet_set_mute",
            "ucnet_get_full_state",
        }


class TestGetTransportState:
    @pytest.mark.asyncio
    async def test_returns_tempo(self, client):
        result = await _dispatch("ucnet_get_transport_state", {}, client)
        data = json.loads(result[0].text)
        assert data["tempo"] == pytest.approx(120.0)

    @pytest.mark.asyncio
    async def test_returns_is_playing(self, client):
        result = await _dispatch("ucnet_get_transport_state", {}, client)
        data = json.loads(result[0].text)
        assert data["isPlaying"] == 1

    @pytest.mark.asyncio
    async def test_returns_position(self, client):
        result = await _dispatch("ucnet_get_transport_state", {}, client)
        data = json.loads(result[0].text)
        assert data["position"] == "1.1.1.0"

    @pytest.mark.asyncio
    async def test_missing_paths_return_none(self):
        c = UCNETClient("127.0.0.1")  # empty cache
        result = await _dispatch("ucnet_get_transport_state", {}, c)
        data = json.loads(result[0].text)
        assert data["tempo"] is None
        assert data["isPlaying"] is None


class TestGetChannelState:
    @pytest.mark.asyncio
    async def test_returns_channel_name(self, client):
        result = await _dispatch("ucnet_get_channel_state", {"channel": 0}, client)
        data = json.loads(result[0].text)
        assert data["name"] == "Kick"

    @pytest.mark.asyncio
    async def test_returns_fader_level(self, client):
        result = await _dispatch("ucnet_get_channel_state", {"channel": 0}, client)
        data = json.loads(result[0].text)
        assert data["fader"] == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_returns_mute_state(self, client):
        result = await _dispatch("ucnet_get_channel_state", {"channel": 1}, client)
        data = json.loads(result[0].text)
        assert data["mute"] == 1

    @pytest.mark.asyncio
    async def test_includes_channel_index(self, client):
        result = await _dispatch("ucnet_get_channel_state", {"channel": 3}, client)
        data = json.loads(result[0].text)
        assert data["channel"] == 3


class TestSetFader:
    @pytest.mark.asyncio
    async def test_set_fader_writes_to_client(self, client):
        client._session = MagicMock()
        client._session.write = MagicMock(return_value=None)

        async def fake_write(data):
            pass
        client._session.write = fake_write

        result = await _dispatch("ucnet_set_fader", {"channel": 0, "level": 0.8}, client)
        assert result[0].text.startswith("OK")
        assert "0.800" in result[0].text

    @pytest.mark.asyncio
    async def test_set_fader_updates_cache(self, client):
        from unittest.mock import AsyncMock
        client._session = AsyncMock()
        await _dispatch("ucnet_set_fader", {"channel": 0, "level": 0.9}, client)
        assert client.get_parameter("/mixer/channel[0]/fader") == pytest.approx(0.9)


class TestSetMute:
    @pytest.mark.asyncio
    async def test_set_mute_true(self, client):
        from unittest.mock import AsyncMock
        client._session = AsyncMock()
        result = await _dispatch("ucnet_set_mute", {"channel": 0, "muted": True}, client)
        assert "ON" in result[0].text

    @pytest.mark.asyncio
    async def test_set_mute_false(self, client):
        from unittest.mock import AsyncMock
        client._session = AsyncMock()
        result = await _dispatch("ucnet_set_mute", {"channel": 0, "muted": False}, client)
        assert "OFF" in result[0].text

    @pytest.mark.asyncio
    async def test_set_mute_updates_cache(self, client):
        from unittest.mock import AsyncMock
        client._session = AsyncMock()
        await _dispatch("ucnet_set_mute", {"channel": 0, "muted": True}, client)
        assert client.get_parameter("/mixer/channel[0]/mute") == 1


class TestGetFullState:
    @pytest.mark.asyncio
    async def test_returns_all_cached_paths(self, client):
        result = await _dispatch("ucnet_get_full_state", {}, client)
        data = json.loads(result[0].text)
        assert "/transport/tempo" in data
        assert "/mixer/channel[0]/name" in data

    @pytest.mark.asyncio
    async def test_empty_cache_returns_empty_object(self):
        c = UCNETClient("127.0.0.1")
        result = await _dispatch("ucnet_get_full_state", {}, c)
        data = json.loads(result[0].text)
        assert data == {}


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self, client):
        with pytest.raises(ValueError, match="Unknown UCNET tool"):
            await _dispatch("ucnet_nonexistent", {}, client)
