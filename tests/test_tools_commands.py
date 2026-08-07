"""Tests for studio_pro_mcp.tools.commands."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from studio_pro_mcp.keystrokes import KeystrokeError
from studio_pro_mcp.tools.commands import _command_tools, _dispatch, resolve

_CATALOG = {
    "Edit|Undo": {"label": "Undo", "package": None, "shortcut": "ctrl+z"},
    "Edit|Redo": {"label": "Redo", "package": None, "shortcut": "ctrl+y"},
    "Track|Duplicate Track Up": {"label": "Duplicate Track Up", "package": None, "shortcut": None},
    "Track|Duplicate Track Down": {
        "label": "Duplicate Track Down", "package": None, "shortcut": None
    },
    "Macros|Macro QWRkIEVR": {"label": "Add EQ", "package": None, "shortcut": None},
    "File|Save New Version...": {"label": "Save New Version...", "package": None, "shortcut": None},
}


class TestToolList:
    def test_returns_three_tools(self) -> None:
        names = {t.name for t in _command_tools()}
        assert names == {
            "studio_one_run_command",
            "studio_one_list_commands",
            "studio_one_save_new_version",
        }


class TestResolve:
    def test_exact_match(self) -> None:
        key, entry = resolve("undo", _CATALOG)
        assert entry["label"] == "Undo"
        assert key == "Edit|Undo"

    def test_case_insensitive(self) -> None:
        key, entry = resolve("UNDO", _CATALOG)
        assert entry["label"] == "Undo"

    def test_unique_substring_match(self) -> None:
        key, entry = resolve("add eq", _CATALOG)
        assert entry["label"] == "Add EQ"

    def test_ambiguous_substring_returns_list(self) -> None:
        match = resolve("duplicate track", _CATALOG)
        assert isinstance(match, list)
        assert len(match) == 2

    def test_no_match_returns_none(self) -> None:
        assert resolve("nonexistent command xyz", _CATALOG) is None


class TestDispatch:
    @pytest.mark.asyncio
    async def test_run_command_calls_palette_with_label(self) -> None:
        with (
            patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG),
            patch(
                "studio_pro_mcp.tools.commands.run_via_command_palette", new_callable=AsyncMock
            ) as mock_palette,
        ):
            result = await _dispatch("studio_one_run_command", {"name": "undo"})
        mock_palette.assert_awaited_once_with("Undo", confirm_dialog=False)
        assert "Ran 'Undo'" in result[0].text
        assert "[Edit]" in result[0].text

    @pytest.mark.asyncio
    async def test_run_command_unknown_reports_error(self) -> None:
        with patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG):
            result = await _dispatch("studio_one_run_command", {"name": "nope"})
        assert result[0].text.startswith("ERROR")

    @pytest.mark.asyncio
    async def test_run_command_ambiguous_reports_candidates(self) -> None:
        with patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG):
            result = await _dispatch("studio_one_run_command", {"name": "duplicate track"})
        assert "Ambiguous" in result[0].text

    @pytest.mark.asyncio
    async def test_run_command_keystroke_error_reports_error(self) -> None:
        with (
            patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG),
            patch(
                "studio_pro_mcp.tools.commands.run_via_command_palette",
                new_callable=AsyncMock,
                side_effect=KeystrokeError("no window"),
            ),
        ):
            result = await _dispatch("studio_one_run_command", {"name": "undo"})
        assert result[0].text == "ERROR: no window"

    @pytest.mark.asyncio
    async def test_list_commands_filters(self) -> None:
        with patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG):
            result = await _dispatch("studio_one_list_commands", {"filter": "duplicate"})
        assert "2 command(s)" in result[0].text
        assert "Duplicate Track" in result[0].text

    @pytest.mark.asyncio
    async def test_list_commands_no_filter_returns_all(self) -> None:
        with patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG):
            result = await _dispatch("studio_one_list_commands", {})
        assert f"{len(_CATALOG)} command(s)" in result[0].text

    @pytest.mark.asyncio
    async def test_save_new_version_uses_confirm_dialog(self) -> None:
        with (
            patch("studio_pro_mcp.tools.commands.load_catalog", return_value=_CATALOG),
            patch(
                "studio_pro_mcp.tools.commands.run_via_command_palette", new_callable=AsyncMock
            ) as mock_palette,
        ):
            result = await _dispatch("studio_one_save_new_version", {})
        mock_palette.assert_awaited_once_with("Save New Version...", confirm_dialog=True)
        assert "Ran 'Save New Version...'" in result[0].text

    @pytest.mark.asyncio
    async def test_empty_catalog_reports_error(self) -> None:
        with patch("studio_pro_mcp.tools.commands.load_catalog", return_value={}):
            result = await _dispatch("studio_one_run_command", {"name": "undo"})
        assert result[0].text.startswith("ERROR")
        assert "generate_command_catalog" in result[0].text
