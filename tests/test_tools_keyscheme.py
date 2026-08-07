"""Tests for studio_pro_mcp.tools.keyscheme_tools."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from studio_pro_mcp.tools.keyscheme_tools import _dispatch, _keyscheme_tools

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<Commands name="Studio App">
    <Command category="Edit" name="Undo">
        <Key name="Ctrl+Z"/>
    </Command>
    <Command category="Macros" name="Macro {macro_b64}"/>
</Commands>
"""


def _write_sample(tmp_path: Path) -> Path:
    macro_b64 = base64.b64encode(b"Add EQ").decode()
    path = tmp_path / "custom.keyscheme"
    path.write_text(_SAMPLE.format(macro_b64=macro_b64), encoding="utf-8")
    return path


class TestToolDefinition:
    def test_generate_catalog_tool_listed(self) -> None:
        names = {t.name for t in _keyscheme_tools()}
        assert "studio_one_generate_command_catalog" in names

    def test_path_and_output_are_optional(self) -> None:
        tool = next(t for t in _keyscheme_tools() if t.name == "studio_one_generate_command_catalog")
        assert tool.input_schema["required"] == []


class TestGenerateCatalog:
    @pytest.mark.asyncio
    async def test_generates_from_custom_path(self, tmp_path: Path) -> None:
        source = _write_sample(tmp_path)
        output = tmp_path / "out.json"
        result = await _dispatch(
            "studio_one_generate_command_catalog",
            {"path": str(source), "output": str(output)},
        )
        assert "OK" in result[0].text
        assert output.is_file()

    @pytest.mark.asyncio
    async def test_written_catalog_contains_decoded_macro(self, tmp_path: Path) -> None:
        source = _write_sample(tmp_path)
        output = tmp_path / "out.json"
        await _dispatch(
            "studio_one_generate_command_catalog",
            {"path": str(source), "output": str(output)},
        )
        data = json.loads(output.read_text(encoding="utf-8"))
        macro_entries = [v for v in data["catalog"].values() if v["label"] == "Add EQ"]
        assert len(macro_entries) == 1

    @pytest.mark.asyncio
    async def test_missing_custom_path_reports_error(self, tmp_path: Path) -> None:
        result = await _dispatch(
            "studio_one_generate_command_catalog",
            {"path": str(tmp_path / "nope.keyscheme")},
        )
        assert result[0].text.startswith("ERROR")

    @pytest.mark.asyncio
    async def test_no_autodiscovery_result_reports_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "studio_pro_mcp.tools.keyscheme_tools.discover_keyscheme", lambda: None
        )
        result = await _dispatch("studio_one_generate_command_catalog", {})
        assert "ERROR" in result[0].text
        assert "auto-discover" in result[0].text.lower() or "found" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_summary_reports_counts(self, tmp_path: Path) -> None:
        source = _write_sample(tmp_path)
        output = tmp_path / "out.json"
        result = await _dispatch(
            "studio_one_generate_command_catalog",
            {"path": str(source), "output": str(output)},
        )
        text = result[0].text
        assert "2 scanned" in text
        assert "1 with a shortcut" in text
        assert "1 macro(s) decoded" in text

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown keyscheme tool"):
            await _dispatch("not_a_tool", {})
