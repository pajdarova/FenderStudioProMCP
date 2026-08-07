# CLAUDE.md — project state

Working notes for Claude Code sessions on this repository. Written 2026-08-07.
This file is a handoff, not documentation. User-facing docs live in `WINDOWS.md`.
Superseded an earlier undated handoff that existed only in chat, not on disk.

---

## 1. What this project is

A fork of `tiwadara/StudioOneMcp`, an MCP server that lets an LLM drive a DAW.
The upstream project targets macOS only. This fork adds Windows support and is
drifting toward a different architecture.

| | |
|---|---|
| Fork | `https://github.com/pajdarova/StudioOneMcp` (`origin`) |
| Upstream | `https://github.com/tiwadara/StudioOneMcp` (`upstream`) |
| Branch | `windows-support` |
| Local path | `C:\Users\adp\Documents\_DEVEL_\FenderStudioProMCP` |
| Licence | MIT |

**Target DAW:** Fender Studio Pro 8 — the rebranded PreSonus Studio One 8, not a
new product.

**Confirmed on this machine** (previously only guessed):
- Settings/keyscheme folder: `%APPDATA%\Fender\Studio Pro 8\` (not `PreSonus`)
- Macro export folder: `Documents\Studio Pro\Macros` (not `Studio One`)
- `user.keyscheme` has 1751 commands, 266 with a translatable shortcut, 471 macros

---

## 2. Ground rules

**Verified means it ran on the user's Windows machine.** Nothing else counts.
**The user tests; Claude cannot.** There is no Windows DAW on Claude's side.
**Prefer data from the user's own installation** over hard-coded tables —
`keymap.json` shipped Studio One 7 shortcuts and three were simply wrong here.
**Do not trust upstream's README** — it claims MIDI-to-command dispatch is
verified; the source disagrees (§4).

---

## 3. Committed / in-progress work (this session)

- `keyscheme.py`: `parse_keyscheme()` now emits a `catalog` — every command
  from the `.keyscheme` (not just ones with a shortcut), with macro names
  decoded from Base64 (`decode_macro_name()`). 471/471 macros decode correctly
  against the real export.
- `tools/keyscheme_tools.py` (new): MCP tool
  `studio_one_generate_command_catalog` — lets the user regenerate the catalog
  themselves from chat, either auto-discovered or from an arbitrary file path
  (their own export, saved elsewhere). Wired into `server.py`.
- `plugin_db.py`: `_prefs_dirs()` now probes `Fender` before `PreSonus` as
  vendor folder, confirmed correct.
- `server.py`: rebuilt on `mcp>=2.0.0`'s `Server(on_list_tools=, on_call_tool=)`
  constructor callbacks; added `--transport {stdio,http}` +
  `--http-host`/`--http-port` to the CLI. Verified with real `mcp.client`
  sessions over both transports.
- `pyproject.toml`: `mcp>=1.0.0,<2` → `mcp>=2.0.0`; added `uvicorn>=0.30`
  (server.py now drives it directly for the HTTP transport).
- `.gitignore`: added `*.keyscheme` — these exports carry the user's real
  installed macro/plugin list and shouldn't land in a public fork.
- `macro_writer.py`: `_macros_dir()` now probes `Studio Pro` before
  `Studio One`, confirmed correct.
- Tests added: `tests/test_keyscheme.py`, `tests/test_tools_keyscheme.py`.
- **Not yet committed to git** — working tree has these changes uncommitted.

---

## 4. Findings that shape the design

### MIDI-to-command dispatch is unproven and probably collides

`MCPPadsComponent.js` carries a comment saying command dispatch from that
surface never fired and the work was shelved, contradicting the README.
Likely cause: `MCPPads.surface.xml` occupies CC 0–127 on channel 1 and CC
0–95 on channel 2, colliding with Mackie Control's V-Pots/jog wheel/encoder
feedback on the same channel, sent over the same port. `studio_one_run_command`
dispatches through this path, so it inherits the problem.

### `Ctrl+K` opens a command palette — the practical dispatch route

`Help|Find Command`, bound to `Ctrl+K`, expects the readable name (e.g.
`Add 4th above`), not the internal Base64 identifier. This reaches all 1751
commands/471 macros without any control surface. Needs text entry via
`KEYEVENTF_UNICODE` (layout-independent) in `keystrokes.py` — not yet built.

### `.keyscheme` beats the HTML export

XML gives one element per shortcut and internal command names (what surfaces
address); HTML gives display names, which differ for ~118 commands. Use XML.

### Clipboard is a dead end for MIDI note data

The DAW doesn't put copied MIDI on the Windows clipboard. `songreader.py`
(uncommitted, from an earlier session) parses `.song` files directly instead —
see §6.

---

## 5. New roadmap (user request, 2026-08-07)

Five asks, not yet sequenced or scoped in detail:

1. **DONE (2026-08-07).** Dual transport. `server.py` now supports
   `--transport stdio` (default, unchanged Claude Desktop config) and
   `--transport http --http-host 127.0.0.1 --http-port 8765`, built from the
   same `_build_server()`/`MidiBridge`. See `WINDOWS.md` "Local HTTP
   transport". Verified with real `mcp.client` sessions over both transports
   (48 tools listed, `mixer_get_state` called successfully over HTTP).
2. **DONE (2026-08-07).** Upgraded to `mcp>=2.0.0`. `Server` moved from
   `@server.list_tools()`/`@server.call_tool()` decorators to constructor
   callbacks (`on_list_tools`, `on_call_tool`); `InitializationOptions`
   construction replaced by `server.create_initialization_options()`.
   `Tool.inputSchema` also renamed to `Tool.input_schema` in 2.0 (construction
   still accepts `inputSchema=` via alias, but attribute reads and static
   typing need the new name) — updated across all six `tools/*.py` modules
   and their tests. Zero changes to tool *dispatch logic* — only the
   constructor keyword and `server.py`'s registration shape changed.
3. **LLM-driven dispatch with minimal user involvement**, built on `Ctrl+K` +
   the generated catalog (§3, §4): user describes intent in natural language,
   LLM resolves it to catalog entries and fires them. For non-trivial/risky
   operations, snapshot first — a `.song` backup copy, or (preferred, since
   Fender Studio Pro supports it) create a new song version before acting.
4. **Finish the MIDI control path** the upstream author started (§4) — worth
   one real experiment now that ports would be split (§7 old roadmap: MCU /
   command / notes on separate loopback ports) rather than sharing one.
5. **Read + transform audio (MIDI/WAV), write it back.** Flagged by the user
   themselves as the hard one. MIDI note read already exists via
   `songreader.py` (uncommitted); WAV read/transform/write-back is unstarted
   and needs its own design (which audio ops, how "write back" reaches the
   DAW — replace file on disk vs. some import trigger).

**Not yet decided:** which of these to tackle first, and in what order. #2
(SDK upgrade) is a prerequisite for #1 (HTTP transport) — check what API the
current `mcp` release actually exposes before committing to an approach for
either.

---

## 6. Uncommitted work from an earlier session (still not integrated)

### `songreader.py` — reads notes out of `.song` files

A `.song` is a ZIP; note data sits in `Performances/Track/*.musicx` in a
small self-describing binary container (`{`/`}` object, `[`/`]` array, `i`
one byte, `D` big-endian double). Note fields: `pitch` (MIDI number), `start`,
`length` (quarter notes), `velocity`. Velocity: `stored = (midi - 1) / 126`,
confirmed against 40/60/80/100% → 51/76/102/127. MIDI 60 is `C3` in this DAW,
configurable via `--middle-c`. Verified against one four-note test file only —
expect unknown markers in real material.

### `clipboard_probe.py` — clipboard format inspector

Diagnostic only, not part of the product. Answered the "is clipboard viable"
question (§4) — keep it around, don't productionize it.

---

## 7. Traps

- `git commit -a` skips untracked files — new modules were nearly left out once.
- **RESOLVED (2026-08-07):** the `mcp<2` pin trap no longer applies —
  `server.py` now targets `mcp>=2.0.0` directly (§5 #2). No venv existed for
  this project before this session; one now lives at `.venv/`.
- `tests/test_tools_transport.py`, `test_tools_mixer.py`, and part of
  `test_midi_bridge.py` fail on this real Windows machine independent of the
  `mcp` version — the `bridge` fixture patches `rtmidi.MidiOut` but
  `MidiBridge._open_existing_port()` (the Windows-only loopback-attach path)
  still calls through to a `MagicMock().get_ports()` that isn't shaped like a
  real port list, so it raises `MidiBridgeError` instead of using the mock.
  Confirmed via `git stash` that this predates every change made this
  session. Not yet fixed — needs the fixture updated to mock
  `get_ports()`/`open_port()` realistically for the Windows branch.
- `keymap.json` defaults are unreliable; prefer the generated
  `shortcuts.json`/`catalog`.
- Do not assume a shortcut works because it's in `keymap.json` — `s` sent
  Solo, not Split, and silently soloed a track during testing.
- No Windows equivalent of the macOS Undo-label verification — nothing
  confirms an action actually took effect once dispatched.
