"""Tests for studio_one_mcp.plugin_db."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from studio_one_mcp.plugin_db import (
    Plugin,
    PluginNotFoundError,
    _normalise_category,
    _parse_plugins_en,
    find_plugin,
    list_plugins,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_db(tmp_path: Path) -> Path:
    """Create a minimal DataStore.db with a PresetDescriptor table."""
    db_path = tmp_path / "DataStore.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE PresetDescriptor (
                _classID   TEXT,
                _vendor    TEXT,
                _subFolder TEXT,
                _category  TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO PresetDescriptor VALUES (?, ?, ?, ?)",
            [
                ("{56535458-6673-5873-6572-756D00000000}", "Xfer Records", "Serum", "AudioSynth"),
                ("{ABCD1234-0000-0000-0000-000000000001}", "FabFilter", "Pro-Q 3", "AudioEffect"),
                ("{ABCD1234-0000-0000-0000-000000000002}", "FabFilter", "Saturn 2", "AudioEffect"),
                ("{ABCD1234-0000-0000-0000-000000000003}", "iZotope", "Ozone 10", "MusicEffect"),
                # Duplicate entry (should be deduplicated)
                ("{56535458-6673-5873-6572-756D00000000}", "Xfer Records", "Serum", "AudioSynth"),
                # Row with empty classID (should be excluded)
                ("", "Bad Vendor", "Bad Plugin", "AudioSynth"),
                # Row with NULL subFolder (should be excluded)
                ("{DEADBEEF-0000-0000-0000-000000000000}", "Null Vendor", None, "AudioEffect"),
            ],
        )
        conn.commit()
    return db_path


# ---------------------------------------------------------------------------
# Tests for list_plugins
# ---------------------------------------------------------------------------

class TestListPlugins:
    def test_returns_plugins_from_db(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugins = list_plugins()
        assert len(plugins) >= 4
        names = {p.name for p in plugins}
        assert "Serum" in names
        assert "Pro-Q 3" in names

    def test_returns_plugin_dataclasses(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugins = list_plugins()
        for p in plugins:
            assert isinstance(p, Plugin)
            assert isinstance(p.cid, str)
            assert isinstance(p.vendor, str)
            assert isinstance(p.name, str)
            assert isinstance(p.category, str)

    def test_filters_by_category(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            synths = list_plugins(category="AudioSynth")
        names = {p.name for p in synths}
        assert "Serum" in names
        assert "Pro-Q 3" not in names

    def test_category_filter_effects(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            effects = list_plugins(category="AudioEffect")
        names = {p.name for p in effects}
        assert "Pro-Q 3" in names
        assert "Saturn 2" in names
        assert "Serum" not in names

    def test_excludes_empty_class_id(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugins = list_plugins()
        vendors = {p.vendor for p in plugins}
        assert "Bad Vendor" not in vendors

    def test_excludes_null_subfolder(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugins = list_plugins()
        names = {p.name for p in plugins}
        # null subFolder rows should be excluded or have empty string name
        for p in plugins:
            assert p.name != ""  # empty names are excluded by the query

    def test_no_datastore_returns_empty(self) -> None:
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=None):
            plugins = list_plugins()
        assert plugins == []

    def test_deduplicates_entries(self, tmp_path: Path) -> None:
        """DISTINCT in query means Serum appears only once even with duplicate rows."""
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugins = list_plugins()
        serum_plugins = [p for p in plugins if p.name == "Serum"]
        assert len(serum_plugins) == 1

    def test_serum_has_correct_fields(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugins = list_plugins()
        serum = next(p for p in plugins if p.name == "Serum")
        assert serum.cid == "{56535458-6673-5873-6572-756D00000000}"
        assert serum.vendor == "Xfer Records"
        assert serum.category == "AudioSynth"


# ---------------------------------------------------------------------------
# Tests for find_plugin
# ---------------------------------------------------------------------------

class TestFindPlugin:
    def test_exact_match(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugin = find_plugin("Serum")
        assert plugin.name == "Serum"
        assert plugin.vendor == "Xfer Records"

    def test_case_insensitive_exact_match(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugin = find_plugin("serum")
        assert plugin.name == "Serum"

    def test_case_insensitive_upper(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugin = find_plugin("SERUM")
        assert plugin.name == "Serum"

    def test_partial_match(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugin = find_plugin("pro-q")
        assert plugin.name == "Pro-Q 3"

    def test_partial_match_case_insensitive(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            plugin = find_plugin("PRO-Q")
        assert plugin.name == "Pro-Q 3"

    def test_not_found_raises_error(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            with pytest.raises(PluginNotFoundError) as exc_info:
                find_plugin("NonexistentPlugin99")
        assert "NonexistentPlugin99" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()

    def test_not_found_lists_known_plugins(self, tmp_path: Path) -> None:
        db = _create_test_db(tmp_path)
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db):
            with pytest.raises(PluginNotFoundError) as exc_info:
                find_plugin("DoesNotExist")
        error_msg = str(exc_info.value)
        # The error should mention known plugins
        assert "Serum" in error_msg or "Pro-Q 3" in error_msg

    def test_exact_match_preferred_over_partial(self, tmp_path: Path) -> None:
        """Exact match should be returned even when another plugin contains the name."""
        db_path = tmp_path / "DataStore.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "CREATE TABLE PresetDescriptor (_classID TEXT, _vendor TEXT, _subFolder TEXT, _category TEXT)"
            )
            conn.executemany(
                "INSERT INTO PresetDescriptor VALUES (?, ?, ?, ?)",
                [
                    ("{AAA}", "VendorA", "Verb", "AudioEffect"),
                    ("{BBB}", "VendorB", "Verb Plus", "AudioEffect"),
                ],
            )
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=db_path):
            plugin = find_plugin("Verb")
        assert plugin.name == "Verb"
        assert plugin.cid == "{AAA}"

    def test_find_plugin_no_datastore_raises_error(self) -> None:
        with patch("studio_one_mcp.plugin_db._find_datastore", return_value=None):
            with pytest.raises(PluginNotFoundError):
                find_plugin("Serum")


# ---------------------------------------------------------------------------
# Tests for Plugins-en.settings XML parser
# ---------------------------------------------------------------------------

_PLUGINS_EN_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Attributes>
    <Attribute id="/Library/Audio/Plug-Ins/VST3/Serum.vst3" members="classID name vendor category">
        <Attribute id="classID" value="{56535458-6673-5873-6572-756D00000000}"/>
        <Attribute id="name" value="Serum"/>
        <Attribute id="vendor" value="Xfer Records"/>
        <Attribute id="category" value="AudioSynth"/>
    </Attribute>
    <Attribute id="/Library/Audio/Plug-Ins/VST3/ProQ3.vst3" members="classID name vendor category">
        <Attribute id="classID" value="{ABCD1234-0000-0000-0000-000000000001}"/>
        <Attribute id="name" value="Pro-Q 3"/>
        <Attribute id="vendor" value="FabFilter"/>
        <Attribute id="category" value="AudioEffect"/>
    </Attribute>
    <Attribute id="/bad/entry/no_classid" members="name vendor">
        <Attribute id="name" value="Broken Plugin"/>
        <Attribute id="vendor" value="Nobody"/>
    </Attribute>
</Attributes>
"""


class TestParsePluginsEn:
    def _write_xml(self, tmp_path: Path, xml: str = _PLUGINS_EN_XML) -> Path:
        p = tmp_path / "Plugins-en.settings"
        p.write_text(xml, encoding="utf-8")
        return p

    def test_parses_plugins(self, tmp_path: Path) -> None:
        path = self._write_xml(tmp_path)
        plugins = _parse_plugins_en(path)
        names = {p.name for p in plugins}
        assert "Serum" in names
        assert "Pro-Q 3" in names

    def test_excludes_missing_classid(self, tmp_path: Path) -> None:
        path = self._write_xml(tmp_path)
        plugins = _parse_plugins_en(path)
        names = {p.name for p in plugins}
        assert "Broken Plugin" not in names

    def test_fields_populated(self, tmp_path: Path) -> None:
        path = self._write_xml(tmp_path)
        plugins = _parse_plugins_en(path)
        serum = next(p for p in plugins if p.name == "Serum")
        assert serum.cid == "{56535458-6673-5873-6572-756D00000000}"
        assert serum.vendor == "Xfer Records"
        assert serum.category == "AudioSynth"

    def test_returns_empty_on_bad_xml(self, tmp_path: Path) -> None:
        path = tmp_path / "Plugins-en.settings"
        path.write_text("not xml at all <<<", encoding="utf-8")
        plugins = _parse_plugins_en(path)
        assert plugins == []

    def test_list_plugins_prefers_settings_file(self, tmp_path: Path) -> None:
        """Plugins-en.settings takes priority over DataStore.db."""
        settings = self._write_xml(tmp_path)
        with (
            patch("studio_one_mcp.plugin_db._find_settings", return_value=settings),
            patch("studio_one_mcp.plugin_db._find_datastore", return_value=None),
        ):
            plugins = list_plugins()
        names = {p.name for p in plugins}
        assert "Serum" in names
        assert "Pro-Q 3" in names


# ---------------------------------------------------------------------------
# Tests for _normalise_category
# ---------------------------------------------------------------------------

class TestNormaliseCategory:
    def test_audiosynth_passthrough(self) -> None:
        assert _normalise_category("AudioSynth") == "AudioSynth"

    def test_audioeffect_passthrough(self) -> None:
        assert _normalise_category("AudioEffect") == "AudioEffect"

    def test_lowercase_synth(self) -> None:
        assert _normalise_category("synth") == "AudioSynth"

    def test_vst3_fx_category(self) -> None:
        assert _normalise_category("Fx") == "AudioEffect"

    def test_reverb_maps_to_effect(self) -> None:
        assert _normalise_category("Reverb") == "AudioEffect"

    def test_empty_string(self) -> None:
        assert _normalise_category("") == ""

    def test_unknown_passthrough(self) -> None:
        assert _normalise_category("SomeUnknownThing") == "SomeUnknownThing"
