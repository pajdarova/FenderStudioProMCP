"""Tests for studio_one_mcp.extension_installer."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from studio_one_mcp.extension_installer import (
    install_extension,
    is_installed,
    uninstall_extension,
)

_PACKAGE_NAME = "StudioOneMCPBridge.package"


def _fake_ext_dir(tmp_path: Path) -> Path:
    """Create a plausible Studio One version directory and return the Extensions path."""
    ext_dir = tmp_path / "PreSonus" / "Studio One 6" / "Extensions"
    # Create the parent (version dir) so _find_extensions_dir picks it up
    ext_dir.parent.mkdir(parents=True, exist_ok=True)
    return ext_dir


class TestInstallExtension:
    def test_installs_package(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            ok, msg = install_extension()
        assert ok
        assert (ext_dir / _PACKAGE_NAME).exists()

    def test_creates_extensions_dir(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        assert not ext_dir.exists()
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
        assert ext_dir.exists()

    def test_installs_extension_xml(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
        assert (ext_dir / _PACKAGE_NAME / "Extension.xml").exists()

    def test_installs_service_js(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
        assert (ext_dir / _PACKAGE_NAME / "Scripts" / "service.js").exists()

    def test_skips_if_already_installed(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
            ok, msg = install_extension()  # second call
        assert ok
        assert "Already installed" in msg

    def test_force_reinstalls(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
            # Drop a sentinel file inside the package to verify it gets replaced
            sentinel = ext_dir / _PACKAGE_NAME / "_sentinel"
            sentinel.write_text("old")
            ok, msg = install_extension(force=True)
        assert ok
        assert not sentinel.exists()

    def test_returns_false_when_no_studio_one(self, tmp_path: Path) -> None:
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=None):
            ok, msg = install_extension()
        assert not ok
        assert "not found" in msg.lower()

    def test_message_mentions_restart(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            _, msg = install_extension()
        assert "Restart" in msg or "restart" in msg


class TestUninstallExtension:
    def test_removes_package(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
            ok, _ = uninstall_extension()
        assert ok
        assert not (ext_dir / _PACKAGE_NAME).exists()

    def test_ok_when_not_installed(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            ok, msg = uninstall_extension()
        assert ok
        assert "not installed" in msg.lower()

    def test_returns_false_when_no_studio_one(self) -> None:
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=None):
            ok, _ = uninstall_extension()
        assert not ok


class TestIsInstalled:
    def test_false_when_not_present(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            assert not is_installed()

    def test_true_after_install(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
            assert is_installed()

    def test_false_after_uninstall(self, tmp_path: Path) -> None:
        ext_dir = _fake_ext_dir(tmp_path)
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=ext_dir):
            install_extension()
            uninstall_extension()
            assert not is_installed()

    def test_false_when_no_studio_one(self) -> None:
        with patch("studio_one_mcp.extension_installer._find_extensions_dir", return_value=None):
            assert not is_installed()
