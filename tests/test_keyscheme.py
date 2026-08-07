"""Tests for studio_pro_mcp.keyscheme."""
from __future__ import annotations

import base64
from pathlib import Path

from studio_pro_mcp.keyscheme import decode_macro_name, parse_keyscheme

# ---------------------------------------------------------------------------
# Tests for decode_macro_name
# ---------------------------------------------------------------------------


class TestDecodeMacroName:
    def test_plain_macro_decodes_label(self) -> None:
        b64 = base64.b64encode(b"Add EQ").decode()
        result = decode_macro_name(f"Macro {b64}")
        assert result == ("Add EQ", None)

    def test_packaged_macro_splits_on_last_dash(self) -> None:
        b64 = base64.b64encode(b"Add 4th above").decode()
        name = f"Macro lruschitzka.harmonywizard.Harmony Wizard-{b64}"
        result = decode_macro_name(name)
        assert result == ("Add 4th above", "lruschitzka.harmonywizard.Harmony Wizard")

    def test_non_macro_command_returns_none(self) -> None:
        assert decode_macro_name("Undo") is None

    def test_invalid_base64_returns_none(self) -> None:
        assert decode_macro_name("Macro not-valid-base64!!!") is None

    def test_unicode_label_roundtrips(self) -> None:
        b64 = base64.b64encode("Přidat kytaru".encode()).decode()
        result = decode_macro_name(f"Macro {b64}")
        assert result == ("Přidat kytaru", None)


# ---------------------------------------------------------------------------
# Tests for parse_keyscheme's catalog
# ---------------------------------------------------------------------------

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<Commands name="Studio App">
    <Command category="Edit" name="Undo">
        <Key name="Ctrl+Z"/>
    </Command>
    <Command category="Edit" name="Redo"/>
    <Command category="Macros" name="Macro {macro_b64}">
        <Key name="Ctrl+E"/>
    </Command>
    <Command category="Macros" name="Macro somevendor.pkg-{packaged_b64}"/>
</Commands>
"""


def _write_sample(tmp_path: Path) -> Path:
    macro_b64 = base64.b64encode(b"Add EQ").decode()
    packaged_b64 = base64.b64encode(b"Add 4th above").decode()
    content = _SAMPLE.format(macro_b64=macro_b64, packaged_b64=packaged_b64)
    path = tmp_path / "sample.keyscheme"
    path.write_text(content, encoding="utf-8")
    return path


class TestParseKeyschemeCatalog:
    def test_every_command_is_in_catalog(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        assert set(data["catalog"]) == {
            "Edit|Undo",
            "Edit|Redo",
            f"Macros|Macro {base64.b64encode(b'Add EQ').decode()}",
            f"Macros|Macro somevendor.pkg-{base64.b64encode(b'Add 4th above').decode()}",
        }

    def test_non_macro_label_is_its_own_name(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        assert data["catalog"]["Edit|Undo"]["label"] == "Undo"
        assert data["catalog"]["Edit|Undo"]["package"] is None

    def test_macro_label_is_decoded(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        key = f"Macros|Macro {base64.b64encode(b'Add EQ').decode()}"
        assert data["catalog"][key]["label"] == "Add EQ"
        assert data["catalog"][key]["package"] is None

    def test_packaged_macro_label_and_package_decoded(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        key = f"Macros|Macro somevendor.pkg-{base64.b64encode(b'Add 4th above').decode()}"
        assert data["catalog"][key]["label"] == "Add 4th above"
        assert data["catalog"][key]["package"] == "somevendor.pkg"

    def test_shortcut_present_when_command_has_key(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        assert data["catalog"]["Edit|Undo"]["shortcut"] == "ctrl+z"

    def test_shortcut_none_when_command_has_no_key(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        assert data["catalog"]["Edit|Redo"]["shortcut"] is None

    def test_macro_count(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        assert data["macro_count"] == 2

    def test_command_count_includes_commands_without_shortcuts(self, tmp_path: Path) -> None:
        data = parse_keyscheme(_write_sample(tmp_path))
        assert data["command_count"] == 4
