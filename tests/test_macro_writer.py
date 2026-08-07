"""Tests for studio_pro_mcp.macro_writer."""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from studio_pro_mcp.macro_writer import (
    MacroCommand,
    macro_command_name,
    write_macro,
)

# ---------------------------------------------------------------------------
# Tests for macro_command_name
# ---------------------------------------------------------------------------

class TestMacroCommandName:
    def test_returns_macro_prefix_plus_base64(self) -> None:
        result = macro_command_name("Insert Serum")
        expected_b64 = base64.b64encode(b"Insert Serum").decode()
        assert result == f"Macro {expected_b64}"

    def test_prefix_is_macro_space(self) -> None:
        result = macro_command_name("Test")
        assert result.startswith("Macro ")

    def test_base64_is_valid(self) -> None:
        result = macro_command_name("My Plugin Macro")
        b64_part = result[len("Macro "):]
        # Should decode without error
        decoded = base64.b64decode(b64_part).decode()
        assert decoded == "My Plugin Macro"

    def test_known_value_serum(self) -> None:
        result = macro_command_name("Insert Serum")
        b64_part = result[len("Macro "):]
        assert base64.b64decode(b64_part) == b"Insert Serum"

    def test_empty_title(self) -> None:
        result = macro_command_name("")
        assert result == "Macro " + base64.b64encode(b"").decode()

    def test_unicode_title(self) -> None:
        title = "Insert Über Plugin"
        result = macro_command_name(title)
        b64_part = result[len("Macro "):]
        decoded = base64.b64decode(b64_part).decode("utf-8")
        assert decoded == title


# ---------------------------------------------------------------------------
# Tests for write_macro
# ---------------------------------------------------------------------------

class TestWriteMacro:
    def test_creates_file(self, tmp_path: Path) -> None:
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro(
                "Insert Serum",
                "MCP",
                [
                    MacroCommand(
                        "Track",
                        "Add Insert to Selected Channels",
                        {"mode": "1", "cid": "{56535458-0000-0000-0000-000000000000}", "preset": "default"},
                    )
                ],
            )
        assert path.exists()

    def test_file_extension(self, tmp_path: Path) -> None:
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("My Macro", "MCP", [MacroCommand("Track", "Do Thing")])
        assert path.suffix == ".studioonemacro"

    def test_xml_declaration(self, tmp_path: Path) -> None:
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("Test Macro", "MCP", [MacroCommand("Cat", "Name")])
        content = path.read_text(encoding="utf-8")
        assert content.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_valid_xml_structure(self, tmp_path: Path) -> None:
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro(
                "Insert Pro-Q 3",
                "MCP",
                [
                    MacroCommand(
                        "Track",
                        "Add Insert to Selected Channels",
                        {"mode": "1", "cid": "{ABCD}", "preset": "default"},
                    ),
                    MacroCommand("Console", "Show Channel Editor"),
                ],
            )
        content = path.read_text(encoding="utf-8")
        # Strip XML declaration for ElementTree parsing
        xml_body = content[content.index("<Macro"):]
        root = ET.fromstring(xml_body)
        assert root.tag == "Macro"
        assert root.attrib["title"] == "Insert Pro-Q 3"
        assert root.attrib["group"] == "MCP"

    def test_macro_attributes(self, tmp_path: Path) -> None:
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("My Title", "MyGroup", [MacroCommand("Cat", "Cmd")])
        content = path.read_text(encoding="utf-8")
        xml_body = content[content.index("<Macro"):]
        root = ET.fromstring(xml_body)
        assert root.attrib["title"] == "My Title"
        assert root.attrib["group"] == "MyGroup"
        assert root.attrib["description"] == ""

    def test_command_elements_count(self, tmp_path: Path) -> None:
        commands = [
            MacroCommand("Track", "Add Insert to Selected Channels", {"mode": "1"}),
            MacroCommand("Console", "Show Channel Editor"),
        ]
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("Test", "MCP", commands)
        content = path.read_text(encoding="utf-8")
        xml_body = content[content.index("<Macro"):]
        root = ET.fromstring(xml_body)
        elements = root.findall("CommandElement")
        assert len(elements) == 2

    def test_command_element_with_arguments(self, tmp_path: Path) -> None:
        commands = [
            MacroCommand(
                "Track",
                "Add Insert to Selected Channels",
                {"mode": "1", "cid": "{TEST-GUID}", "preset": "default"},
            )
        ]
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("Test Args", "MCP", commands)
        content = path.read_text(encoding="utf-8")
        xml_body = content[content.index("<Macro"):]
        root = ET.fromstring(xml_body)
        elem = root.find("CommandElement")
        assert elem is not None
        assert elem.attrib["category"] == "Track"
        assert elem.attrib["name"] == "Add Insert to Selected Channels"
        args = {a.attrib["name"]: a.attrib["value"] for a in elem.findall("CommandArgument")}
        assert args["mode"] == "1"
        assert args["cid"] == "{TEST-GUID}"
        assert args["preset"] == "default"

    def test_command_element_without_arguments(self, tmp_path: Path) -> None:
        commands = [MacroCommand("Console", "Show Channel Editor")]
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("No Args", "MCP", commands)
        content = path.read_text(encoding="utf-8")
        xml_body = content[content.index("<Macro"):]
        root = ET.fromstring(xml_body)
        elem = root.find("CommandElement")
        assert elem is not None
        assert elem.attrib["category"] == "Console"
        assert elem.attrib["name"] == "Show Channel Editor"
        assert len(elem.findall("CommandArgument")) == 0

    def test_safe_filename_generation(self, tmp_path: Path) -> None:
        """Title with special chars should produce a safe filename."""
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("Insert Pro/Q:3", "MCP", [MacroCommand("Cat", "Cmd")])
        # The filename should not contain slashes or colons
        assert "/" not in path.name
        assert ":" not in path.name
        assert path.name.endswith(".studioonemacro")

    def test_xml_escaping_ampersand_in_title(self, tmp_path: Path) -> None:
        """Ampersand in title should be escaped to &amp; so XML is valid."""
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("Insert Kick & Bass", "MCP", [MacroCommand("Cat", "Cmd")])
        content = path.read_text(encoding="utf-8")
        # The raw content should contain the escaped form
        assert "&amp;" in content
        # The XML body (starting from <Macro) should be parseable
        xml_body = content[content.index("<Macro"):]
        root = ET.fromstring(xml_body)
        # After parsing, the attribute should have the literal &
        assert "&" in root.attrib["title"]

    def test_returns_path(self, tmp_path: Path) -> None:
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            result = write_macro("Test", "MCP", [MacroCommand("Cat", "Cmd")])
        assert isinstance(result, Path)

    def test_full_insert_macro_matches_expected_format(self, tmp_path: Path) -> None:
        """Test the full macro format matches the confirmed real file structure."""
        cid = "{56535458-6673-5873-6572-756D00000000}"
        commands = [
            MacroCommand(
                "Track",
                "Add Insert to Selected Channels",
                {"mode": "1", "cid": cid, "preset": "default"},
            ),
            MacroCommand("Console", "Show Channel Editor"),
        ]
        with patch("studio_pro_mcp.macro_writer._macros_dir", return_value=tmp_path):
            path = write_macro("Insert Serum", "MCP", commands)
        content = path.read_text(encoding="utf-8")
        # Check key structural elements
        assert 'title="Insert Serum"' in content
        assert 'group="MCP"' in content
        assert 'category="Track"' in content
        assert 'name="Add Insert to Selected Channels"' in content
        assert f'value="{cid}"' in content
        assert 'category="Console"' in content
        assert 'name="Show Channel Editor"' in content
