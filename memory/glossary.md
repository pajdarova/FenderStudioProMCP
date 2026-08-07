---
name: glossary
description: Decoder ring for terms, tools, and shorthand used in this project
---

# Glossary

- **Fender Studio Pro** — rebrand of PreSonus Studio One after Fender's acquisition. Same DAW, new name/vendor; "Studio Pro 8" corresponds to "Studio One 8".
- **`.keyscheme`** — plain XML file the DAW exports from *Preferences → Keyboard Shortcuts*, listing every command/macro with its internal name and assigned shortcut(s). Source of truth for the generated command catalog (`keyscheme.py`).
- **Catalog** — the per-user command list generated from a `.keyscheme` export (`keyscheme.py`'s `parse_keyscheme()` → `catalog`), keyed `"Category|Name"`, with a decoded readable `label` for macros (whose internal name is Base64). Regenerated via the `studio_one_generate_command_catalog` MCP tool.
- **Ctrl+K palette** — the DAW's command palette (`Help|Find Command`). Accepts a typed readable command/macro name and runs the top match on Enter. Current dispatch mechanism for `studio_one_run_command`, replacing the unreliable MIDI-CC path.
- **MCU** — Mackie Control Universal, a standardized MIDI protocol for DAW control surfaces (faders, pan, mute/solo, transport). Used for `tools/mixer.py`/`tools/transport.py`, over the `StudioOneMCP` virtual/loopback MIDI port.
- **loopMIDI** — third-party Windows tool that creates a loopback MIDI port. Needed because Windows (unlike macOS/Linux) can't create virtual MIDI ports in-process; `python-rtmidi`'s WinMM backend attaches to an existing loopback port instead of creating one.
- **`StudioOneMCP`** (the MIDI port name, all-caps MCP) — deliberately *not* renamed when the rest of the project rebranded to `studio_pro_mcp`/FenderStudioProMCP. A loopMIDI port and a Studio Pro External Device are already bound to this exact name on the dev machine; renaming is scoped into the planned 3-port split (`StudioPro-DAW`/`StudioPro-MIDI`/`StudioPro-SURF`, see `TASKS.md`), not a casual rename.
- **External Device** — Studio Pro's term (Preferences → External Devices) for a bound control surface, e.g. the MCU surface or the (currently unused) `StudioOneMCPPads` command surface.
- **`studio-one-devices/StudioOneMCPPads/`** — the MIDI CC-based command-surface device definition from the original upstream project. Superseded by Ctrl+K dispatch; kept for the pending port-split work, not deleted.
