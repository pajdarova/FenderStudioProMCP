# Phase 3 — Macro Bridge & Command Dispatch

## Milestone: Studio One SDK Fully Reverse-Engineered

Reached by reading the bundled JavaScript source at
`Studio One 6.app/Contents/Resources/sdk/` and the built-in extension
`Contents/Extensions/studioonemacros/scripts/macros.package`.

---

## What We Now Know

### Command Dispatch API

Any Studio One command can be triggered from JS (inside an extension or macro):

```javascript
Host.GUI.Commands.interpretCommand(category, name, defer, attrs);
// attrs = Host.Attributes(["Key1", "Value1", "Key2", "Value2"])
```

`beginTransaction` / `endTransaction` wrap multi-step sequences for a single
undo entry.

### Complete Command Category List

| Category | Example commands |
|----------|-----------------|
| `Arranger` | (arrange-level operations) |
| `Audio` | Normalize Audio, Reverse Audio, Render Event FX |
| `Console` | (mixer operations) |
| `Devices` | (device/plugin operations) |
| `Edit` | Undo, Redo, Split at Cursor, Deselect All, Invert Selection |
| `Event` | Bounce Selection, Merge Events, Toggle Mute, Strip Silence, Transform to Rendered Audio |
| `Macros` | (user/generated macros by base64 name) |
| `Media` | (media pool operations) |
| `Musical Functions` | Select Notes, Apply Scale |
| `Navigation` | Next/Previous Hotspot, Goto Next/Previous Event/Section |
| `Project` | Detect Loudness, Update Mastering Files, Copy Metadata to all Tracks |
| `Show` | Next/Previous Patch, Next/Previous Setlist Item, Select Patch 1–5 |
| `Song` | Show in Explorer/Finder, Copy External Files |
| `Track` | Duplicate (complete), Enable/Disable Track, Find Track/Channel, Hide/Show * Tracks |
| `Transport` | All Notes Off, Set Sync Mode * |
| `View` | Previous/Next Macro Page, Select Macro Page |
| `Zoom` | Zoom to Selection, Zoom Full, Track Height Tiny/Normal/Large |

**Track creation via direct commands (no dialog):**
- `Track` / `Add Audio Track (mono)` — direct, no dialog
- `Track` / `Add Layer` — add comping layer to selected track
- `Track` / `Expand Layers` with `CommandArgument name="Expand" value="1"`

Full Add Track dialog is an `IEditTask` (`trackedit.package`), but the mono
variant is exposed as a plain command callable from macros and the extension.

### Macro File Format (fully reverse-engineered)

File extension: `.studioonemacro`  
Location auto-scanned: `~/Documents/Studio One/Macros/`

```xml
<Macro title="My Macro" group="MCP" description="">
    <CommandElement category="Track" name="Duplicate (complete)"/>
    <CommandElement category="Edit" name="Undo">
        <CommandArgument name="SomeParam" value="SomeValue"/>
    </CommandElement>
</Macro>
```

Studio One watches the Macros folder and registers each file as a command
under category `"Macros"` with name `"Macro " + base64(title)`. Once
registered, it can be triggered via:

```javascript
Host.GUI.Commands.interpretCommand("Macros", "Macro " + btoa(title), false, null);
// Python equivalent: "Macro " + base64.b64encode(title.encode()).decode()
```

### Macro Execution Flow

```
MacroExecuter.execute()
  → beginTransaction(macro.title)
  → for each CommandElement:
      interpretCommand(category, name, false, args)
      postMessage(self, -1, "nextCommand")   // defer to let UI settle
  → endTransaction()
```

---

## Phase 3 Capabilities (Planned)

### Plugin Insertion API

`Track/Add Insert to Selected Channels`:
```xml
<CommandArgument name="mode" value="1"/>
<CommandArgument name="cid" value="{PLUGIN-GUID}"/>
<CommandArgument name="preset" value="default"/>
```

`Audio/Insert Event FX` (same args + optional `tail` = tail seconds).

Known built-in plugin GUIDs:
| Plugin | GUID |
|--------|------|
| Compressor | `{54F19B72-352C-4AA5-A2AF-67F86F30D6BE}` |
| Pro EQ | `{073C4094-E062-4FB5-8328-74608DD1A3A4}` |
| GainTrim | `{E4D7D911-0608-4B46-ABA3-2E345399A5AC}` |
| Space Delay | `{BFBEA41B-679A-41F2-AACA-ED9D51137412}` |
| Open Air (Reverb) | `{29C71194-B29A-40C0-9A35-9053DB6F596C}` |

Additional useful commands:
- `Console` / `Show Channel Editor`
- `Audio` / `Open Event FX Editor`
- `Edit` / `Toggle Ripple Edit` (`State` = `"1"` on, `""` off)
- `Transport` / `Locate Selection`

User Extensions folder (confirmed, directory-based like built-in extensions):
`~/Library/Application Support/PreSonus/Studio One 6/Extensions/`

---

### 3a — Macro Generation

The MCP server writes `.studioonemacro` XML files into
`~/Documents/Studio One/Macros/MCP/`. Studio One picks them up on rescan.
The server then triggers them via keyboard shortcut or a future Extension.

**Use cases:**
- Generate per-plugin macros ("New track with Serum", "Insert Fabfilter Pro-Q")
- Generate session-template macros ("My mix template" = N buses + routing)
- Combine any sequence of `interpretCommand` calls into a single user-triggerable action

### 3b — Extension IPC Bridge (ABANDONED)

> **Status: abandoned.** A JS-Extension file-IPC bridge would need the extension
> to *poll* a watched folder, which requires a timer the Studio One JS runtime
> does not provide. Verified on Studio One 7.2.3 (2026-06): no
> `setInterval`/`setTimeout`, no timer class, `Host.Signals.advise` fires no
> callbacks, `DocumentEventHandler.onDocumentEvent` never fires from a
> classfactory declaration. The control-surface `onIdle` *is* periodic, but its
> JS context has **no `Host` global** — so it can read no files and dispatch no
> commands. The two contexts (file access vs. timer) are isolated.
>
> **Use the push-based paths instead** — they need no timer because the OS /
> Studio One do the work in real time:
> - **Keyboard automation** (`tools/automation.py`) — primary path. See [SETUP.md](../SETUP.md).
> - **Macros** (`macro_writer.py`) — for commands with no shortcut.
> - **MCU MIDI** (`midi_bridge.py`) — transport & mixer.

---

## SDK Files Read

| File | Location | Key findings |
|------|----------|-------------|
| `cclapp.js` | sdk/ | CCL base classes, `Host.Classes.createInstance`, `Host.GUI.*` |
| `engine.js` | sdk/ | Track class IDs, `EditFunctions`, `TrackFormats` |
| `hostutils.js` | sdk/ | `Host.Objects.getObjectByUrl("object://hostapp/...")` |
| `media.js` | sdk/ | `MediaType` enum, `Speakers` enum |
| `devices.js` | sdk/ | `MixerConsole` indices, `ChannelEditorType` constants |
| `trackedit.package` | Scripts/ | Full `AddTrackDialogTask` — track creation API |
| `musicedit.package` | Scripts/ | MIDI editing `IEditTask` |
| `macros.package` | Extensions/ | Command dispatch, macro XML format, `MacroExecuter` |
| `commandbar-v3.xml` | macros.package | All 16 command categories + every command name |
| `elements.js` | macros.package | `CommandElement`, `Macro.saveToFile`, `MacroExecuter` |
| `manager.js` | macros.package | `Host.IO.*`, `Host.FileTypes.registerHandler`, rescan flow |
| `service.js` | macros.package | `FrameworkService` template for our bridge |

---

## Next Steps

1. Verify MIDI-can-trigger-a-macro (bind a MIDI note to a generated macro in
   Studio One) — would give a fully no-Accessibility command path.
2. Exercise the keyboard automation suite end-to-end against a live session.
3. Expand the plugin GUID database for `auto_generate_insert_macro`.
