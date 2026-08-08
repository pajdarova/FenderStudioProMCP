"""Tests for mixer MCP tool dispatchers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from studio_pro_mcp.tools.mixer import _dispatch, _mixer_tools


@pytest.fixture()
def bridge():
    with (
        patch("studio_pro_mcp.midi_bridge.rtmidi.MidiOut") as mock_cls,
        patch("studio_pro_mcp.midi_bridge.rtmidi.MidiIn") as mock_in_cls,
    ):
        mock_out = MagicMock()
        mock_out.get_ports.return_value = ["Test"]
        mock_cls.return_value = mock_out
        mock_in = MagicMock()
        mock_in.get_ports.return_value = ["Test"]
        mock_in_cls.return_value = mock_in
        from studio_pro_mcp.midi_bridge import MidiBridge
        b = MidiBridge(port_name="Test", message_delay=0)
        b.open()
        yield b


class TestToolList:
    def test_returns_eleven_tools(self):
        assert len(_mixer_tools()) == 11

    def test_tool_names(self):
        names = {t.name for t in _mixer_tools()}
        assert "mixer_set_fader" in names
        assert "mixer_toggle_mute" in names
        assert "mixer_toggle_solo" in names
        assert "mixer_toggle_rec_arm" in names
        assert "mixer_select_channel" in names
        assert "mixer_set_pan" in names
        assert "mixer_get_state" in names

    def test_set_fader_schema_requires_channel_and_level(self):
        tool = next(t for t in _mixer_tools() if t.name == "mixer_set_fader")
        assert "channel" in tool.input_schema["required"]
        assert "level" in tool.input_schema["required"]


class TestSetFader:
    @pytest.mark.asyncio
    async def test_set_fader_channel_0(self, bridge):
        result = await _dispatch("mixer_set_fader", {"channel": 0, "level": 50}, bridge)
        assert "0" in result[0].text or "fader" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_set_fader_master(self, bridge):
        result = await _dispatch("mixer_set_fader", {"channel": "master", "level": 75}, bridge)
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_set_fader_updates_assumed_state(self, bridge):
        await _dispatch("mixer_set_fader", {"channel": 3, "level": 60.0}, bridge)
        assert bridge.get_assumed_state()["fader_levels"][3] == pytest.approx(60.0)

    @pytest.mark.asyncio
    async def test_set_fader_invalid_channel_raises(self, bridge):
        with pytest.raises(ValueError):
            await _dispatch("mixer_set_fader", {"channel": 99, "level": 50}, bridge)

    @pytest.mark.asyncio
    async def test_set_fader_level_clamped(self, bridge):
        result = await _dispatch("mixer_set_fader", {"channel": 0, "level": 200}, bridge)
        assert result[0].text.startswith("OK")
        assert bridge.get_assumed_state()["fader_levels"][0] == 100.0


class TestToggleMute:
    @pytest.mark.asyncio
    async def test_toggle_mute_reports_on(self, bridge):
        result = await _dispatch("mixer_toggle_mute", {"channel": 0}, bridge)
        assert "ON" in result[0].text

    @pytest.mark.asyncio
    async def test_toggle_mute_twice_reports_off(self, bridge):
        await _dispatch("mixer_toggle_mute", {"channel": 0}, bridge)
        result = await _dispatch("mixer_toggle_mute", {"channel": 0}, bridge)
        assert "OFF" in result[0].text

    @pytest.mark.asyncio
    async def test_toggle_mute_different_channels_independent(self, bridge):
        await _dispatch("mixer_toggle_mute", {"channel": 0}, bridge)
        await _dispatch("mixer_toggle_mute", {"channel": 1}, bridge)
        assert bridge.get_assumed_state()["mute"][0] is True
        assert bridge.get_assumed_state()["mute"][1] is True


class TestToggleSolo:
    @pytest.mark.asyncio
    async def test_toggle_solo_reports_on(self, bridge):
        result = await _dispatch("mixer_toggle_solo", {"channel": 2}, bridge)
        assert "ON" in result[0].text

    @pytest.mark.asyncio
    async def test_toggle_solo_updates_state(self, bridge):
        await _dispatch("mixer_toggle_solo", {"channel": 4}, bridge)
        assert bridge.get_assumed_state()["solo"][4] is True


class TestToggleRecArm:
    @pytest.mark.asyncio
    async def test_toggle_rec_arm_reports_on(self, bridge):
        result = await _dispatch("mixer_toggle_rec_arm", {"channel": 0}, bridge)
        assert "ON" in result[0].text


class TestSelectChannel:
    @pytest.mark.asyncio
    async def test_select_channel_ok(self, bridge):
        result = await _dispatch("mixer_select_channel", {"channel": 5}, bridge)
        assert result[0].text.startswith("OK")
        assert "5" in result[0].text


class TestSetPan:
    @pytest.mark.asyncio
    async def test_pan_right(self, bridge):
        result = await _dispatch("mixer_set_pan", {"channel": 0, "pan": 20}, bridge)
        assert "right" in result[0].text

    @pytest.mark.asyncio
    async def test_pan_left(self, bridge):
        result = await _dispatch("mixer_set_pan", {"channel": 0, "pan": -20}, bridge)
        assert "left" in result[0].text

    @pytest.mark.asyncio
    async def test_pan_center(self, bridge):
        result = await _dispatch("mixer_set_pan", {"channel": 0, "pan": 0}, bridge)
        assert "center" in result[0].text


class TestGetState:
    @pytest.mark.asyncio
    async def test_get_state_returns_json(self, bridge):
        await _dispatch("mixer_set_fader", {"channel": 0, "level": 80}, bridge)
        result = await _dispatch("mixer_get_state", {}, bridge)
        data = json.loads(result[0].text)
        assert "fader_levels" in data
        assert "mute" in data
        assert "solo" in data

    @pytest.mark.asyncio
    async def test_get_state_reflects_sent_commands(self, bridge):
        await _dispatch("mixer_set_fader", {"channel": 2, "level": 42}, bridge)
        result = await _dispatch("mixer_get_state", {}, bridge)
        data = json.loads(result[0].text)
        assert data["fader_levels"]["2"] == pytest.approx(42.0)


class TestBankNavigation:
    @pytest.mark.asyncio
    async def test_bank_right_advances_bank(self, bridge):
        result = await _dispatch("mixer_bank_right", {}, bridge)
        assert "bank → 1" in result[0].text
        assert bridge.current_bank == 1

    @pytest.mark.asyncio
    async def test_bank_left_at_zero_returns_message(self, bridge):
        result = await _dispatch("mixer_bank_left", {}, bridge)
        assert "bank 0" in result[0].text.lower()
        assert bridge.current_bank == 0

    @pytest.mark.asyncio
    async def test_bank_right_then_left_returns_to_zero(self, bridge):
        await _dispatch("mixer_bank_right", {}, bridge)
        await _dispatch("mixer_bank_left", {}, bridge)
        assert bridge.current_bank == 0

    @pytest.mark.asyncio
    async def test_goto_bank_jumps_directly(self, bridge):
        result = await _dispatch("mixer_goto_bank", {"bank": 3}, bridge)
        assert bridge.current_bank == 3
        assert "ch 25–32" in result[0].text

    @pytest.mark.asyncio
    async def test_goto_bank_clamps_to_max(self, bridge):
        await _dispatch("mixer_goto_bank", {"bank": 99}, bridge)
        assert bridge.current_bank == 7

    @pytest.mark.asyncio
    async def test_get_bank_reports_range(self, bridge):
        await _dispatch("mixer_goto_bank", {"bank": 2}, bridge)
        result = await _dispatch("mixer_get_bank", {}, bridge)
        assert "17–24" in result[0].text

    @pytest.mark.asyncio
    async def test_bank_right_at_max_returns_message(self, bridge):
        await _dispatch("mixer_goto_bank", {"bank": 7}, bridge)
        result = await _dispatch("mixer_bank_right", {}, bridge)
        assert "last bank" in result[0].text.lower()


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self, bridge):
        with pytest.raises(ValueError, match="Unknown mixer tool"):
            await _dispatch("mixer_nonexistent", {}, bridge)
