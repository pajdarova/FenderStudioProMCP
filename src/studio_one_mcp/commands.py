"""Command dispatch layer.

Maps Studio One function names to MIDI CCs (from ``docs/midi-map.json``) and sends
them on the ``StudioOneMCP`` virtual port, where the ``StudioOneMCP Pads`` control
surface turns each CC into a Studio One ``<Command>``.

Only built-in commands are dispatchable this way; user macros do not dispatch from a
control surface (see docs/macros-todo.json) and need a separate trigger.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_MAP_PATH = Path(__file__).resolve().parents[2] / "docs" / "midi-map.json"


def load_map(path: Path | None = None) -> list[dict[str, Any]]:
    with open(path or _MAP_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def resolve(name: str, cmap: list[dict[str, Any]]) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Return the matching function, a list of candidates if ambiguous, or None."""
    n = name.strip().lower()
    for f in cmap:  # exact label
        if f["label"].lower() == n:
            return f
    for f in cmap:  # exact command name
        if f["name"].lower() == n:
            return f
    subs = [f for f in cmap if n in f["label"].lower()]
    if len(subs) == 1:
        return subs[0]
    return subs or None


class CommandDispatcher:
    """Owns the virtual MIDI port and fires commands by name."""

    def __init__(self, port_name: str = "StudioOneMCP") -> None:
        self.port_name = port_name
        self._out: Any = None
        self._map = load_map()

    def open(self) -> None:
        import rtmidi

        from . import coremidi

        import contextlib

        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(self.port_name)
        with contextlib.suppress(Exception):
            coremidi.pin_unique_id(self.port_name)

    def close(self) -> None:
        if self._out is not None:
            self._out.close_port()
            self._out = None

    def send_cc(self, channel: int, cc: int) -> None:
        status = 0xB0 | (channel & 0x0F)
        self._out.send_message([status, cc, 127])
        time.sleep(0.03)
        self._out.send_message([status, cc, 0])

    def run(self, name: str) -> dict[str, Any]:
        f = resolve(name, self._map)
        if f is None:
            raise KeyError(f"No Studio One command matching {name!r}")
        if isinstance(f, list):
            names = ", ".join(x["label"] for x in f[:8])
            raise KeyError(f"Ambiguous {name!r} — candidates: {names}")
        if self._out is None:
            self.open()
        self.send_cc(f["channel"], f["cc"])
        return f

    def list_commands(self) -> list[str]:
        return [f["label"] for f in self._map]
