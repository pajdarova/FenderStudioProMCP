# HISTORY.md — session history

Narrative log of decisions made across Claude Code sessions on this project,
for picking the work back up on a different machine. `CLAUDE.md` is the
current-state handoff (what exists now, what's unverified); this file is the
**why**, in order, so you don't have to reconstruct it from `git log` or
re-explain context to a fresh session.

---

## 2026-08-03 — Windows port (earlier session, not this one)

Ported the upstream (macOS-only) `tiwadara/StudioOneMcp` to Windows:
`SendInput`-based keystrokes, loopback MIDI attach instead of virtual-port
creation, and a `keyscheme.py` module that reads the DAW's own `.keyscheme`
export instead of trusting hard-coded shortcuts — three of the shipped
defaults turned out to be wrong on this installation. Also produced
`songreader.py` (parses note data out of `.song` files) and
`clipboard_probe.py`, both uncommitted, and the finding that MIDI-to-command
dispatch was shelved upstream and likely collides with Mackie Control on the
shared port. Full detail in the git history before `7f9a500`.

## 2026-08-07 — This session

### 1. Per-user command catalog

**Problem:** every user has different installed macros, so a command list
can't ship as a static file. **Decision:** `keyscheme.py`'s `parse_keyscheme()`
now emits a `catalog` — every command in the `.keyscheme`, not just ones with
a shortcut, with macro names decoded from Base64. New MCP tool
`studio_one_generate_command_catalog` lets the user regenerate it themselves,
from either the DAW's own folders or an arbitrary file. Verified against the
real export: 1751 commands, 471/471 macros decoded correctly.

**Side finding, confirmed on this machine:** the vendor folder is `Fender`,
not `PreSonus` (`%APPDATA%\Fender\Studio Pro 8\`), and macro exports go to
`Documents\Studio Pro\Macros`, not `Documents\Studio One\Macros`. Both were
previously guessed. Fixed in `plugin_db.py`/`macro_writer.py`.

### 2. MCP SDK 2.0 upgrade + dual transport

**Problem:** pinned to `mcp<2` because 2.0 removed the
`@server.list_tools()`/`@server.call_tool()` decorator API `server.py` relied
on. **Decision:** rather than rewrite onto the new high-level
`MCPServer`/FastMCP decorator style, adapted to the lowlevel `Server`'s new
constructor callbacks (`on_list_tools`, `on_call_tool`) — zero changes to any
of the six `tools/*.py` dispatch modules. This also unlocked
`Server.streamable_http_app()`, so `--transport {stdio,http}` now serves the
same tools over stdio (Claude Desktop, unchanged default) or local HTTP.
Verified with real `mcp.client` sessions over both transports.

### 3. LICENSE, credits, and the move to its own repo

Neither this fork nor upstream ever shipped a real `LICENSE` file — "MIT" was
only ever a README claim. Added one crediting both `tiwadara` (original) and
this fork. The user then split this project off `pajdarova/StudioOneMcp` into
its own repo, `pajdarova/FenderStudioProMCP` (already MIT-licensed on
GitHub) — merged with `--allow-unrelated-histories -X ours` so the new repo's
initial commit stays in the history and this project's LICENSE (with
attribution) wins the merge. Local `main` now tracks `fender/main`; the old
`windows-support` branch stays local, tracking `origin` (the old fork), untouched.

### 4. Ctrl+K command-palette dispatch replaces MIDI-CC — confirmed live

**Problem:** `studio_one_run_command` dispatched through
`docs/midi-map.json` over MIDI CC — 224 built-ins, zero macros, and
documented as unreliable (channel collision with Mackie Control's V-Pots,
never confirmed firing upstream). **Decision:** resolve against the
per-user catalog (§1) instead, and dispatch by typing the command's readable
name into the DAW's `Ctrl+K` palette (`KEYEVENTF_UNICODE`, layout-independent).
Added `studio_one_save_new_version` for the LLM to call before risky
multi-step work — an explicit tool, not automatic on every command, so it
doesn't fire on trivial single actions.

**This is the first command-dispatch path in the project's history confirmed
to work.** Live-tested against the running DAW with the user watching:
`studio_one_run_command("Undo")` actually undid the last action. Along the
way, discovered that panel toggles like "Toggle Mixer" aren't in the
`.keyscheme` catalog at all (they resolve under a different internal label —
`View|Console`, displayed as `"Console"`) — not a bug, just a naming trap;
logged as an open item.

### 5. Rename to `studio_pro_mcp` / FenderStudioProMCP

Once the project had its own repo, kept the old upstream name
(`studio_one_mcp` package, `studio-one-mcp` CLI, `STUDIO_ONE_MCP_*` env vars,
"StudioOneMcp" in every doc) despite being a substantially different project.
Renamed package/CLI/env-vars/docs to `studio_pro_mcp` / `studio-pro-mcp` /
`STUDIO_PRO_MCP_*` / FenderStudioProMCP. **Deliberately left unchanged:** the
MIDI port name/default (`StudioOneMCP`) and `studio-one-devices/StudioOneMCPPads/`
— a loopMIDI port and a Studio Pro External Device are already bound to that
exact name on this machine, and renaming it is scoped into the pending
3-port split (below), not a find-and-replace.

---

## Open items (tracked in `TASKS.md`, `C:\Users\adp\test\TASKS.md` — outside this repo)

- **Untested:** whether `studio_one_run_command` can fire the 8 commands whose
  `.keyscheme` shortcut didn't translate (multimedia keys, `#`) — Ctrl+K
  dispatch only needs the readable label, not the shortcut, so this may
  already be moot, just unverified.
- **Planned:** split the single `StudioOneMCP` MIDI port into three —
  `StudioPro-DAW` (Mackie Control), `StudioPro-MIDI` (note read/write, ties
  into the still-uncommitted `songreader.py`), `StudioPro-SURF`
  (command-surface dispatch — no functional code currently uses this path,
  superseded by Ctrl+K). Needs its own plan; touches `midi_bridge.py`,
  `coremidi.py`, `tools/mixer.py`, `tools/transport.py`, and the
  `studio-one-devices/` surface files.

## Roadmap not yet started

From the original five-item ask (2026-08-07): #1 (dual transport) and #2 (SDK
upgrade) done (§2 above); #3 (LLM dispatch) done for built-in commands and
partially verified for macros (§4); #4 (finish the MIDI control path) folded
into the port-split item above; #5 (read/transform audio — MIDI via
`songreader.py`, WAV unstarted) not begun.
