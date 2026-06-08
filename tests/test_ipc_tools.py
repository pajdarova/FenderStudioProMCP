"""Tests for studio_one_mcp.tools.ipc_tools."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from studio_one_mcp.ipc_bridge import IPCBridge, IPCError, IPCResponse, IPCTimeoutError
from studio_one_mcp.tools.ipc_tools import _dispatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_bridge(tmp_path: Path) -> IPCBridge:
    bridge = MagicMock(spec=IPCBridge)
    bridge.dispatch = AsyncMock(return_value=IPCResponse(id="x", ok=True, error=None))
    return bridge


def _timeout_bridge(tmp_path: Path) -> IPCBridge:
    bridge = MagicMock(spec=IPCBridge)
    bridge.dispatch = AsyncMock(side_effect=IPCTimeoutError("timed out"))
    return bridge


def _error_bridge(tmp_path: Path) -> IPCBridge:
    bridge = MagicMock(spec=IPCBridge)
    bridge.dispatch = AsyncMock(side_effect=IPCError("command failed"))
    return bridge


def _text(result: list) -> str:
    return result[0].text


# ---------------------------------------------------------------------------
# install_ipc_extension
# ---------------------------------------------------------------------------

class TestInstallIpcExtension:
    @pytest.mark.asyncio
    async def test_ok_result(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        with patch(
            "studio_one_mcp.tools.ipc_tools.install_extension",
            return_value=(True, "Installed to /some/path"),
        ):
            result = await _dispatch("install_ipc_extension", {}, bridge)
        assert "OK" in _text(result)

    @pytest.mark.asyncio
    async def test_error_result(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        with patch(
            "studio_one_mcp.tools.ipc_tools.install_extension",
            return_value=(False, "Studio One user data directory not found."),
        ):
            result = await _dispatch("install_ipc_extension", {}, bridge)
        assert "ERROR" in _text(result)

    @pytest.mark.asyncio
    async def test_force_flag_passed(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        with patch(
            "studio_one_mcp.tools.ipc_tools.install_extension",
            return_value=(True, "Installed"),
        ) as mock_install:
            await _dispatch("install_ipc_extension", {"force": True}, bridge)
        mock_install.assert_called_once_with(force=True)


# ---------------------------------------------------------------------------
# dispatch_command
# ---------------------------------------------------------------------------

class TestDispatchCommand:
    @pytest.mark.asyncio
    async def test_success(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        result = await _dispatch(
            "dispatch_command", {"category": "Track", "name": "Add Audio Track (mono)"}, bridge
        )
        assert "OK" in _text(result)
        assert "Track/Add Audio Track (mono)" in _text(result)

    @pytest.mark.asyncio
    async def test_passes_args_and_transaction(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch(
            "dispatch_command",
            {
                "category": "Edit",
                "name": "Undo",
                "args": {"key": "val"},
                "transaction": "My tx",
                "timeout": 3.0,
            },
            bridge,
        )
        bridge.dispatch.assert_awaited_once_with(
            "Edit", "Undo", args={"key": "val"}, transaction="My tx", timeout=3.0
        )

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_text(self, tmp_path: Path) -> None:
        bridge = _timeout_bridge(tmp_path)
        result = await _dispatch(
            "dispatch_command", {"category": "X", "name": "Y"}, bridge
        )
        assert "TIMEOUT" in _text(result)

    @pytest.mark.asyncio
    async def test_error_returns_error_text(self, tmp_path: Path) -> None:
        bridge = _error_bridge(tmp_path)
        result = await _dispatch(
            "dispatch_command", {"category": "X", "name": "Y"}, bridge
        )
        assert "ERROR" in _text(result)


# ---------------------------------------------------------------------------
# create_audio_track
# ---------------------------------------------------------------------------

class TestCreateAudioTrack:
    @pytest.mark.asyncio
    async def test_dispatches_correct_command(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch("create_audio_track", {}, bridge)
        bridge.dispatch.assert_awaited_once()
        call_args = bridge.dispatch.call_args
        assert call_args[0][0] == "Track"
        assert call_args[0][1] == "Add Audio Track (mono)"

    @pytest.mark.asyncio
    async def test_success_message(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        result = await _dispatch("create_audio_track", {}, bridge)
        assert "OK" in _text(result)

    @pytest.mark.asyncio
    async def test_timeout_message(self, tmp_path: Path) -> None:
        bridge = _timeout_bridge(tmp_path)
        result = await _dispatch("create_audio_track", {}, bridge)
        assert "TIMEOUT" in _text(result)


# ---------------------------------------------------------------------------
# create_instrument_track
# ---------------------------------------------------------------------------

class TestCreateInstrumentTrack:
    @pytest.mark.asyncio
    async def test_dispatches_add_instrument_track(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch("create_instrument_track", {}, bridge)
        first_call = bridge.dispatch.call_args_list[0]
        assert first_call[0][0] == "Track"
        assert first_call[0][1] == "Add Instrument Track"

    @pytest.mark.asyncio
    async def test_inserts_plugin_when_cid_provided(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch(
            "create_instrument_track", {"plugin_cid": "{MY-GUID}"}, bridge
        )
        assert bridge.dispatch.await_count == 2
        second_call = bridge.dispatch.call_args_list[1]
        assert second_call[0][1] == "Add Insert to Selected Channels"
        assert second_call[1]["args"]["cid"] == "{MY-GUID}"

    @pytest.mark.asyncio
    async def test_no_insert_when_no_cid(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch("create_instrument_track", {}, bridge)
        assert bridge.dispatch.await_count == 1

    @pytest.mark.asyncio
    async def test_timeout_message(self, tmp_path: Path) -> None:
        bridge = _timeout_bridge(tmp_path)
        result = await _dispatch("create_instrument_track", {}, bridge)
        assert "TIMEOUT" in _text(result)


# ---------------------------------------------------------------------------
# insert_plugin_direct
# ---------------------------------------------------------------------------

class TestInsertPluginDirect:
    @pytest.mark.asyncio
    async def test_requires_plugin_cid(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        result = await _dispatch("insert_plugin_direct", {}, bridge)
        assert "ERROR" in _text(result)
        bridge.dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatches_insert_command(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch("insert_plugin_direct", {"plugin_cid": "{GUID}"}, bridge)
        bridge.dispatch.assert_awaited_once()
        call_kwargs = bridge.dispatch.call_args[1]
        assert call_kwargs["args"]["cid"] == "{GUID}"
        assert call_kwargs["args"]["mode"] == "1"

    @pytest.mark.asyncio
    async def test_uses_custom_preset(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch(
            "insert_plugin_direct", {"plugin_cid": "{GUID}", "preset": "My Preset"}, bridge
        )
        call_kwargs = bridge.dispatch.call_args[1]
        assert call_kwargs["args"]["preset"] == "My Preset"

    @pytest.mark.asyncio
    async def test_wraps_in_transaction(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        await _dispatch("insert_plugin_direct", {"plugin_cid": "{GUID}"}, bridge)
        call_kwargs = bridge.dispatch.call_args[1]
        assert call_kwargs["transaction"] == "Insert plugin"

    @pytest.mark.asyncio
    async def test_success_message(self, tmp_path: Path) -> None:
        bridge = _ok_bridge(tmp_path)
        result = await _dispatch("insert_plugin_direct", {"plugin_cid": "{GUID}"}, bridge)
        assert "OK" in _text(result)

    @pytest.mark.asyncio
    async def test_timeout_message(self, tmp_path: Path) -> None:
        bridge = _timeout_bridge(tmp_path)
        result = await _dispatch("insert_plugin_direct", {"plugin_cid": "{GUID}"}, bridge)
        assert "TIMEOUT" in _text(result)

    @pytest.mark.asyncio
    async def test_error_message(self, tmp_path: Path) -> None:
        bridge = _error_bridge(tmp_path)
        result = await _dispatch("insert_plugin_direct", {"plugin_cid": "{GUID}"}, bridge)
        assert "ERROR" in _text(result)
