"""Installs the StudioOneMCPBridge Extension into Studio One's user Extensions folder."""
from __future__ import annotations

import platform
import shutil
from pathlib import Path

_PACKAGE_NAME = "StudioOneMCPBridge.package"
_BUNDLE_SRC = Path(__file__).parent / "extension" / _PACKAGE_NAME


def _extensions_dirs() -> list[Path]:
    """Candidate Extensions directories in priority order (newest Studio One first)."""
    system = platform.system()
    dirs: list[Path] = []
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "PreSonus"
        for ver in ("Studio One 7", "Studio One 6", "Studio One 5"):
            dirs.append(base / ver / "Extensions")
    elif system == "Windows":
        import os
        appdata = Path(os.environ.get("APPDATA", str(Path.home())))
        for ver in ("Studio One 7", "Studio One 6", "Studio One 5"):
            dirs.append(appdata / "PreSonus" / ver / "Extensions")
    return dirs


def _find_extensions_dir() -> Path | None:
    """Return the Extensions directory for the installed Studio One version."""
    for d in _extensions_dirs():
        if d.parent.exists():  # version dir exists → Studio One is installed
            return d
    return None


def install_extension(force: bool = False) -> tuple[bool, str]:
    """Copy StudioOneMCPBridge.package into Studio One's Extensions folder.

    Parameters
    ----------
    force:
        Re-install even if the extension is already present.

    Returns
    -------
    (success, message)
    """
    ext_dir = _find_extensions_dir()
    if ext_dir is None:
        return False, (
            "Studio One user data directory not found. "
            "Is Studio One installed?"
        )

    dest = ext_dir / _PACKAGE_NAME
    if dest.exists() and not force:
        return True, f"Already installed at {dest}"

    if dest.exists():
        shutil.rmtree(dest)

    ext_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_BUNDLE_SRC, dest)
    return True, (
        f"Installed to {dest}\n"
        "Restart Studio One to activate the StudioOneMCPBridge extension."
    )


def uninstall_extension() -> tuple[bool, str]:
    """Remove StudioOneMCPBridge.package from Studio One's Extensions folder."""
    ext_dir = _find_extensions_dir()
    if ext_dir is None:
        return False, "Studio One user data directory not found."
    dest = ext_dir / _PACKAGE_NAME
    if not dest.exists():
        return True, "Extension not installed."
    shutil.rmtree(dest)
    return True, f"Removed {dest}"


def is_installed() -> bool:
    """Return True if the extension package is present in the Extensions folder."""
    ext_dir = _find_extensions_dir()
    if ext_dir is None:
        return False
    return (ext_dir / _PACKAGE_NAME).exists()
