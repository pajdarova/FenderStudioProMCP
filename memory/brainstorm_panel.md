---
name: brainstorm-panel
description: Brainstorm — global-hotkey overlay panel for LLM commands + MIDI/audio round-trip with FSP
metadata:
  type: brainstorm
---

# Brainstorm: overlay panel + MIDI/audio round-trip (2026-08-07)

## The idea

A panel triggered by a global keyboard shortcut, opening above all windows,
letting the user type natural-language requests to an LLM directly — plus a
drop zone for MIDI/audio files the LLM would transform and hand back,
ready to drag into Fender Studio Pro.

## Conclusions

1. **The panel itself is low-risk to build.** It's a natural client for the
   `--transport http` work already done today — a lightweight app (not yet
   decided: Python/Tkinter-PySide vs. Tauri) talking to
   `studio-pro-mcp --transport http`, rather than going through Claude
   Desktop. Global hotkey registration on Windows reuses the same `ctypes`
   toolkit already in `keystrokes.py` (`RegisterHotKey`).

2. **Dragging content *out* of FSP via OS drag-and-drop does not work** —
   already established in an earlier session (see `HISTORY.md` §"Clipboard
   is a dead end"). FSP accepts drags *into* its track area but won't let a
   clip be dragged out to another application (unlike Cubase, which can).
   So "drag from FSP into the panel" as a mechanism is a dead end — already
   ruled out, not a new finding.

3. **Reframing "what's selected" — don't introspect, dispatch an export
   instead.** There's no API to ask the DAW what's currently selected. Rather
   than trying to read live selection state, use the existing Ctrl+K
   dispatch to run a command that *acts on* the selection and writes it to a
   file:
   - `Event|Export Selection` is in the real catalog and **confirmed working
     by the user, live-tested** (2026-08-07).
   - **Caveat, user-confirmed:** the export dialog offers a format choice,
     and it must be set to **MIDI file**, not **MIDI loop** — the wrong
     format was the default/first attempt. Any automated dispatch of this
     command needs to account for that dialog step (a `confirm_dialog`-style
     follow-up, similar to `studio_one_save_new_version`'s handling of
     `Save New Version...`'s naming dialog) and pick the MIDI-file option
     specifically, not just press Enter blind.

4. **Proposed flow once the panel exists:**
   1. User selects a clip in FSP, presses the hotkey → panel opens.
   2. Panel/LLM calls `studio_one_run_command("Export Selection")`
      (format: MIDI file) → DAW exports the current selection to a file.
   3. A `songreader.py`-style parser reads that specific export (not the
      whole `.song`).
   4. LLM transforms it; result appears in the panel.
   5. User drags the result **from the panel into FSP** — this direction is
      fine, importing external MIDI/audio into a DAW is standard, unlike the
      dead-end direction in point 2.

5. **WAV round-trip (roadmap item 5) is a separate, larger problem** and
   deliberately not folded into the panel work. Unlike MIDI, there's no
   existing reader/writer, and "transform" is undefined (EQ? generation?
   stem separation?) — needs its own scoping before any implementation.

6. **Voice input (added 2026-08-08).** Just another input mode feeding the
   same text → LLM → MCP pipeline the panel already has — speech-to-text
   turns voice into text, then it's handled identically to typed input. No
   new "understanding" logic needed.

   - **Local Whisper, not cloud STT** — consistent with the project running
     entirely local (no MIDI/audio ever leaves the machine); avoids sending
     studio audio to a third party and avoids network latency.
   - **Push-to-talk, not always-listening** — safer (no accidental trigger),
     more private, and this is a *music production* tool: the user is
     realistically going to want voice commands while audio is actively
     playing through speakers, which the mic will also pick up. Push-to-talk
     limits the window but doesn't eliminate the problem — expect it to work
     best with playback stopped or with a headset mic.
   - **Code-switching risk:** the user speaks Czech, but command/macro/plugin
     names are English ("Add EQ", "Bounce Selection") — mixed-language
     utterances are a known weak spot for STT models, expect more
     transcription errors here than for pure single-language speech.
   - **Risk-scaled confirmation, not blanket confirmation.** An LLM in the
     loop already self-corrects a lot of STT noise (mirrors
     `tools/commands.py:resolve()`'s existing ambiguous-match handling —
     ask instead of guessing). But it can't catch the more dangerous case:
     Whisper confidently swapping one *valid* word for another (e.g. "Undo"
     misheard as "Redo") — both parse as unambiguous commands, so nothing
     signals the LLM anything is wrong. Mitigation: reuse the same
     reversible/irreversible split already established for
     `studio_one_save_new_version` — low-risk, reversible actions (Undo,
     panel toggles, navigation) execute straight from voice; anything hard
     to reverse shows what the LLM understood in the panel and waits for
     confirmation before dispatching.

## Not yet decided

- Panel tech stack (Python GUI vs. Tauri/Electron).
- Exact automation sequence for the `Export Selection` dialog (which
  keystrokes/clicks select "MIDI file" specifically — not yet tested this
  precisely, only that the *format choice* matters).
- Where exported files should land (fixed temp path? user-configurable?) so
  the reader knows where to look.
- Whether this replaces or complements the existing MCP-client-based
  workflow (Claude Desktop / other MCP clients still work over stdio
  regardless of whether the panel gets built).
- Voice: which local Whisper variant/size (latency vs. accuracy trade-off
  untested), exact push-to-talk hotkey, and where the reversible/irreversible
  line actually gets drawn for auto-execute vs. confirm-first.
