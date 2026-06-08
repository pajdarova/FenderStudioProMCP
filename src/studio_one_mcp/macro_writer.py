"""Generates .studioonemacro XML files and places them in the user's Macros folder."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape


@dataclass
class MacroCommand:
    category: str
    name: str
    arguments: dict[str, str] = field(default_factory=dict)


def _macros_dir() -> Path:
    base = Path.home() / "Documents" / "Studio One" / "Macros" / "MCP"
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_macro(title: str, group: str, commands: list[MacroCommand]) -> Path:
    """Write a .studioonemacro XML file. Returns the path written."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Macro title="{escape(title)}" group="{escape(group)}" description="">',
    ]
    for cmd in commands:
        if cmd.arguments:
            lines.append(
                f'    <CommandElement category="{escape(cmd.category)}" name="{escape(cmd.name)}">'
            )
            for k, v in cmd.arguments.items():
                lines.append(f'        <CommandArgument name="{escape(k)}" value="{escape(v)}"/>')
            lines.append("    </CommandElement>")
        else:
            lines.append(
                f'    <CommandElement category="{escape(cmd.category)}" name="{escape(cmd.name)}"/>'
            )
    lines.append("</Macro>")
    safe = "".join(c if c.isalnum() or c in " -_()" else "_" for c in title).strip()
    path = _macros_dir() / f"{safe}.studioonemacro"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def macro_command_name(title: str) -> str:
    """Return the Studio One command name for a macro ('Macro ' + base64(title))."""
    return "Macro " + base64.b64encode(title.encode()).decode()
