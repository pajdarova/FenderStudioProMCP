---
name: glossary
description: Decoder ring for terms, tools, and shorthand used in this project
---

# Glossary

- **Fender Studio Pro** — rebrand of PreSonus Studio One after Fender's acquisition. Same DAW, new name/vendor; "Studio Pro 8" corresponds to "Studio One 8".
- **`.keyscheme`** — plain XML file the DAW exports from *Preferences → Keyboard Shortcuts*, listing every command/macro with its internal name and assigned shortcut(s). Source of truth for the generated command catalog (`keyscheme.py`).
- **Catalog** — the per-user command list generated from a `.keyscheme` export (`keyscheme.py`'s `parse_keyscheme()` → `catalog`), keyed `"Category|Name"`, with a decoded readable `label` for macros (whose internal name is Base64). Regenerated via the `studio_one_generate_command_catalog` MCP tool.
- **Ctrl+K palette** — the DAW's command palette (`Help|Find Command`). Accepts a typed readable command/macro name and runs the top match on Enter. Current dispatch mechanism for `studio_one_run_command`, replacing the unreliable MIDI-CC path.
- **MCU** — Mackie Control Universal, a standardized MIDI protocol for DAW control surfaces (faders, pan, mute/solo, transport). Used for `tools/mixer.py`/`tools/transport.py`, over the `StudioPro-MCU` virtual/loopback MIDI port. Chosen over HUI (older, coarser, mainly a Pro Tools-compatibility protocol) — MCU has finer fader resolution and richer LCD/metering support.
- **loopMIDI** — third-party Windows tool that creates a loopback MIDI port. Needed because Windows (unlike macOS/Linux) can't create virtual MIDI ports in-process; `python-rtmidi`'s WinMM backend attaches to an existing loopback port instead of creating one.
- **`StudioPro-MCU`** (renamed 2026-08-08 from `StudioOneMCP`) — the MIDI port `MidiBridge` opens/attaches to. Requires a manual one-time step on each machine: recreate the loopMIDI port under this name and repoint the DAW's Mackie Control Universal External Device's "Receive From" at it (see `TASKS.md`).
- **`StudioOneMCP Pads`** (the SURF control-surface device, `studio-one-devices/StudioOneMCPPads/`) — deliberately *not* renamed; its CC-based command dispatch is dead code (Ctrl+K/direct shortcuts replaced it, see `memory/2026-08.md` §11–12). Kept for a possible future revival, not wired to anything today.
- **External Device** — Studio Pro's term (Preferences → External Devices) for a bound control surface, e.g. the MCU surface or the (currently unused) `StudioOneMCPPads` command surface.
- **`studio-one-devices/StudioOneMCPPads/`** — the MIDI CC-based command-surface device definition from the original upstream project. Superseded by Ctrl+K dispatch; kept for the pending port-split work, not deleted.
- **`external/`** — local-only reference material (gitignored 2026-08-08, deliberately never committed): the Emagic Logic Control MIDI Implementation manual (copyrighted, real distribution risk if pushed to this public repo — source: [Mackie Control Universal DIY Guide](https://sites.google.com/view/mackiecontroluniversaldiyguide/home)) and a Studio Pro keyboard-shortcuts HTML export. Doesn't sync via git — copy these over manually if working from a different machine and they're needed again.
