"""Tests for transport MCP tool dispatchers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from studio_pro_mcp.tools.transport import _dispatch, _transport_tools


@pytest.fixture()
def bridge():
    with patch("studio_pro_mcp.midi_bridge.rtmidi.MidiOut") as mock_cls:
        mock_out = MagicMock()
        mock_out.get_ports.return_value = ["Test"]
        mock_cls.return_value = mock_out
        from studio_pro_mcp.midi_bridge import MidiBridge
        b = MidiBridge(port_name="Test", message_delay=0)
        b.open()
        yield b


class TestToolList:
    def test_returns_nine_tools(self):
        tools = _transport_tools()
        assert len(tools) == 9

    def test_all_tools_have_names(self):
        names = {t.name for t in _transport_tools()}
        expected = {
            "transport_play", "transport_stop", "transport_record",
            "transport_rewind", "transport_fast_forward", "transport_toggle_loop",
            "transport_save", "transport_undo", "transport_redo",
        }
        assert names == expected

    def test_all_tools_have_empty_input_schema(self):
        for tool in _transport_tools():
            assert tool.input_schema["required"] == []


class TestDispatch:
    @pytest.mark.asyncio
    async def test_play_calls_bridge_play(self, bridge):
        result = await _dispatch("transport_play", {}, bridge)
        assert result[0].text.startswith("OK")
        assert bridge._out.send_message.called

    @pytest.mark.asyncio
    async def test_stop_calls_bridge_stop(self, bridge):
        result = await _dispatch("transport_stop", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_record_calls_bridge_record(self, bridge):
        result = await _dispatch("transport_record", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_rewind_calls_bridge_rewind(self, bridge):
        result = await _dispatch("transport_rewind", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_fast_forward_calls_bridge(self, bridge):
        result = await _dispatch("transport_fast_forward", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_toggle_loop_calls_bridge(self, bridge):
        result = await _dispatch("transport_toggle_loop", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_save_calls_bridge(self, bridge):
        result = await _dispatch("transport_save", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_undo_calls_bridge(self, bridge):
        result = await _dispatch("transport_undo", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_redo_calls_bridge(self, bridge):
        result = await _dispatch("transport_redo", {}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self, bridge):
        with pytest.raises(ValueError, match="Unknown transport tool"):
            await _dispatch("transport_nonexistent", {}, bridge)

    @pytest.mark.asyncio
    async def test_result_is_list_of_text_content(self, bridge):
        from mcp.types import TextContent
        result = await _dispatch("transport_play", {}, bridge)
        assert isinstance(result, list)
        assert isinstance(result[0], TextContent)
        assert result[0].type == "text"
