# MEMORY.md — session history & memory index

Narrative log of decisions made across Claude Code sessions on this project,
for picking the work back up on a different machine. `CLAUDE.md` is the
current-state handoff (what exists now, what's unverified); this file is the
**why**, in order, so you don't have to reconstruct it from `git log` or
re-explain context to a fresh session. Also indexes `memory/` (see bottom).

Supersedes `HISTORY.md`, which this file replaces.

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

## 2026-08-07 — Long session: SDK 2.0, Ctrl+K dispatch, rebrand

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
attribution) wins the merge. Local `main` now tracks `fender/main`. The old
`pajdarova/StudioOneMcp` fork was later deleted by the user once full history
preservation was verified (`git log fender/main..origin/*` empty on both
`main` and `windows-support`).

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
3-port split (see `TASKS.md`), not a find-and-replace.

### 6. CI was never actually green — fixed the real reasons

Pushing to the new repo surfaced that `mypy --strict` had been failing on CI
(`ubuntu-latest`) since Windows support landed, unnoticed because local
sessions only compared "error count vs. before my change," not exit code.
Two distinct causes, both platform-divergence traps:

- **mypy:** `ctypes.WinDLL` only exists in typeshed's win32-conditional
  stubs. Reproduced locally with `mypy src --platform linux`; fixed by
  pinning `platform = "win32"` in `[tool.mypy]` so CI and a Windows dev
  machine see the same stubs regardless of which OS actually runs mypy.
  Also deleted `src/studio_pro_mcp/commands.py` — the old MIDI-CC
  dispatcher, unreferenced since §4, whose `Any`-leaking `load_map()` was
  one of the mypy failures.
- **pytest:** the inverse trap. `test_tools_transport.py`/`test_tools_mixer.py`
  fail locally on this Windows machine (`MidiBridge._open_existing_port()`,
  the Windows-only loopback-attach path, doesn't match how the `bridge`
  fixture mocks `rtmidi.MidiOut`) but **pass cleanly on Linux CI**, because
  `MidiBridge.open()` takes the `open_virtual_port()` branch there instead.
  So: green CI is not proof these MIDI paths work on Windows — they test a
  code path Windows never executes. Fixture still needs fixing; tracked in
  `TASKS.md`... actually not yet added there either — see Open items below.

### 7. Project state moved fully into this repo

Two follow-ups after the rename, both about not depending on any single
machine's local state:

- `TASKS.md` and `memory/glossary.md` added directly to this repo (previously
  the open items lived in `C:\Users\adp\test\TASKS.md`, which isn't a git
  repo — the user considered making it one, then decided project state
  belongs in the project's own repo instead, since that's what already syncs
  across her machines via `git pull`/`push`).
- `C:\Users\adp\test` itself confirmed to be an onboarding/practice space
  from getting familiar with Claude Code, not a real project — recorded in
  the assistant's own cross-session memory so future sessions don't
  over-weight it.

### 8. Brainstorm: overlay panel + MIDI/audio round-trip

Design discussion, not implementation — full writeup in
`memory/brainstorm_panel.md`. Headline conclusions: a global-hotkey overlay
panel is a natural client for the `--transport http` work (§2); dragging
content *out* of FSP via OS drag-and-drop is a confirmed dead end from an
earlier session; `Event|Export Selection` sidesteps the "what's currently
selected" problem (no API for that) by dispatching a command that acts on
the selection instead of introspecting it — **user confirmed this works
live**, with the caveat that the export format must be set to **MIDI file**,
not **MIDI loop**.

---

## Open items

(Previously said "tracked in `C:\Users\adp\test\TASKS.md`" — stale as of §7;
they're in this repo's own `TASKS.md` now.)

- Whether `studio_one_run_command` can fire the 8 commands whose `.keyscheme`
  shortcut didn't translate (multimedia keys, `#`) — likely moot since
  Ctrl+K dispatch only needs the label, but unverified.
- The 3-port MIDI split (`StudioPro-DAW`/`StudioPro-MIDI`/`StudioPro-SURF`).
- Linux (low priority) — Fender Studio Pro has native virtual-MIDI support
  there, but the Ctrl+K keystroke path doesn't exist for Linux at all yet
  (only a stale, un-exercised `xdotool` branch).
- **Not yet added to `TASKS.md`:** fix the `bridge` test fixture so
  `test_tools_transport.py`/`test_tools_mixer.py` actually exercise the
  Windows `_open_existing_port()` path correctly (§6).
- Overlay panel + MIDI export/import round-trip — see §8 and
  `memory/brainstorm_panel.md`, nothing decided on implementation yet.

## Roadmap not yet started

From the original five-item ask (2026-08-07): #1 (dual transport) and #2 (SDK
upgrade) done (§2 above); #3 (LLM dispatch) done for built-in commands and
partially verified for macros (§4); #4 (finish the MIDI control path) folded
into the port-split item above; #5 (read/transform audio — MIDI via
`songreader.py` plus the `Export Selection` approach from §8, WAV unstarted)
not begun.

---

## Index of `memory/`

- `memory/glossary.md` — decoder ring for project-specific terms (`.keyscheme`,
  catalog, Ctrl+K palette, MCU, loopMIDI, `StudioOneMCP`, External Device).
- `memory/brainstorm_panel.md` — design discussion for a global-hotkey
  overlay panel + MIDI/audio round-trip with FSP (§8 above).
