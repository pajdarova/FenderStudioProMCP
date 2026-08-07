"""Unit tests for keystrokes module (parsing helpers, no OS calls)."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from studio_pro_mcp.keystrokes import (
    _AS_KEY_CODES,
    KeystrokeError,
    _combo_to_applescript,
    _platform_key,
    _send_unicode_text,
    _split_combo,
    _win32,
    load_keymap,
    run_via_command_palette,
)


class TestSplitCombo:
    def test_single_key(self):
        mods, key = _split_combo("t")
        assert mods == []
        assert key == "t"

    def test_modifier_and_key(self):
        mods, key = _split_combo("cmd+z")
        assert mods == ["cmd"]
        assert key == "z"

    def test_multiple_modifiers(self):
        mods, key = _split_combo("ctrl+shift+cmd+i")
        assert mods == ["ctrl", "shift", "cmd"]
        assert key == "i"

    def test_normalises_to_lowercase(self):
        mods, key = _split_combo("CMD+SHIFT+Z")
        assert mods == ["cmd", "shift"]
        assert key == "z"


class TestComboToApplescript:
    def test_plain_key(self):
        result = _combo_to_applescript("t")
        assert result == 'keystroke "t"'

    def test_cmd_modifier(self):
        result = _combo_to_applescript("cmd+z")
        assert "command down" in result
        assert '"z"' in result

    def test_multiple_modifiers(self):
        result = _combo_to_applescript("ctrl+shift+cmd+i")
        assert "control down" in result
        assert "shift down" in result
        assert "command down" in result
        assert '"i"' in result

    def test_special_key_uses_key_code(self):
        result = _combo_to_applescript("return")
        assert "key code" in result
        assert str(_AS_KEY_CODES["return"]) in result

    def test_special_key_with_modifier(self):
        result = _combo_to_applescript("cmd+backspace")
        assert "key code" in result
        assert "command down" in result

    def test_f3_uses_key_code(self):
        result = _combo_to_applescript("f3")
        assert "key code" in result
        assert str(_AS_KEY_CODES["f3"]) in result

    def test_space_uses_key_code(self):
        result = _combo_to_applescript("space")
        assert "key code" in result


class TestPlatformKey:
    def test_returns_known_value(self):
        result = _platform_key()
        assert result in ("mac", "windows", "linux")

    def test_darwin_maps_to_mac(self):
        with patch("platform.system", return_value="Darwin"):
            assert _platform_key() == "mac"

    def test_windows_maps_to_windows(self):
        with patch("platform.system", return_value="Windows"):
            assert _platform_key() == "windows"

    def test_linux_maps_to_linux(self):
        with patch("platform.system", return_value="Linux"):
            assert _platform_key() == "linux"


@pytest.mark.skipif(platform.system() != "Windows", reason="_win32() needs ctypes.WinDLL")
class TestSendUnicodeText:
    def test_sends_keyeventf_unicode_down_and_up_per_char(self):
        w = _win32()
        calls: list[tuple[int, int, int]] = []

        def fake_send_input(count, array, _size):
            for i in range(count):
                calls.append((array[i].ki.wVk, array[i].ki.wScan, array[i].ki.dwFlags))
            return count

        keyeventf_unicode = 0x0004
        keyeventf_keyup = 0x0002
        with patch.object(w.user32, "SendInput", side_effect=fake_send_input):
            _send_unicode_text("A!")

        assert calls == [
            (0, ord("A"), keyeventf_unicode),
            (0, ord("A"), keyeventf_unicode | keyeventf_keyup),
            (0, ord("!"), keyeventf_unicode),
            (0, ord("!"), keyeventf_unicode | keyeventf_keyup),
        ]

    def test_raises_on_short_send(self):
        w = _win32()
        with (
            patch.object(w.user32, "SendInput", return_value=0),
            pytest.raises(KeystrokeError, match="failed to type"),
        ):
            _send_unicode_text("x")


class TestRunViaCommandPalette:
    @pytest.mark.asyncio
    async def test_non_windows_raises(self):
        with (
            patch("platform.system", return_value="Darwin"),
            pytest.raises(KeystrokeError, match="Windows-only"),
        ):
            await run_via_command_palette("Undo")

    @pytest.mark.asyncio
    async def test_windows_delegates_to_blocking_helper(self):
        with (
            patch("platform.system", return_value="Windows"),
            patch(
                "studio_pro_mcp.keystrokes._run_via_command_palette_blocking"
            ) as mock_blocking,
        ):
            await run_via_command_palette("Add EQ", confirm_dialog=True)
        mock_blocking.assert_called_once_with("Studio One", "Add EQ", confirm_dialog=True)


class TestLoadKeymap:
    def test_loads_default_keymap(self):
        km = load_keymap()
        assert "actions" in km
        assert "app_name" in km

    def test_default_keymap_has_undo(self):
        km = load_keymap()
        assert "undo" in km["actions"]

    def test_default_keymap_has_add_audio_track(self):
        km = load_keymap()
        assert "add_audio_track" in km["actions"]

    def test_custom_keymap_via_env(self, tmp_path: Path):
        custom = {
            "app_name": {"mac": "Studio One", "windows": "Studio One", "linux": "Studio One"},
            "actions": {"my_action": {"mac": {"keys": ["cmd+x"]}}},
        }
        keymap_file = tmp_path / "custom_keymap.json"
        keymap_file.write_text(json.dumps(custom))

        with patch.dict("os.environ", {"STUDIO_PRO_MCP_KEYMAP": str(keymap_file)}):
            km = load_keymap()
        assert "my_action" in km["actions"]

    def test_missing_keymap_raises(self, tmp_path: Path):
        with (
            patch.dict("os.environ", {"STUDIO_PRO_MCP_KEYMAP": str(tmp_path / "nope.json")}),
            pytest.raises(KeystrokeError, match="Keymap not found"),
        ):
            load_keymap()

    def test_invalid_json_raises(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        with (
            patch.dict("os.environ", {"STUDIO_PRO_MCP_KEYMAP": str(bad)}),
            pytest.raises(KeystrokeError, match="Invalid keymap JSON"),
        ):
            load_keymap()


class TestToolDispatcher:
    @pytest.mark.asyncio
    async def test_known_tool_returns_ok(self):
        from unittest.mock import AsyncMock, patch

        from studio_pro_mcp.tools.automation import _dispatch
        with patch("studio_pro_mcp.tools.automation.send_action", new_callable=AsyncMock) as mock_send:
            result = await _dispatch("auto_undo", {})
        mock_send.assert_awaited_once_with("undo")
        assert result[0].text.startswith("OK")

    @pytest.mark.asyncio
    async def test_keystroke_error_returns_error_text(self):
        from unittest.mock import AsyncMock, patch

        from studio_pro_mcp.tools.automation import _dispatch
        with patch(
            "studio_pro_mcp.tools.automation.send_action",
            new_callable=AsyncMock,
            side_effect=KeystrokeError("xdotool not found"),
        ):
            result = await _dispatch("auto_undo", {})
        assert "ERROR" in result[0].text

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self):
        from studio_pro_mcp.tools.automation import _dispatch
        with pytest.raises(ValueError, match="Unknown automation tool"):
            await _dispatch("auto_nonexistent", {})
