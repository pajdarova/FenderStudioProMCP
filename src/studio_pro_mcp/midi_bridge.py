"""MCU-over-MIDI bridge: opens a virtual MIDI port and sends Mackie Control Universal messages."""

from __future__ import annotations

import logging
import platform
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import rtmidi
from rtmidi.midiconstants import CONTROL_CHANGE, NOTE_ON, PITCH_BEND

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCU note numbers (all on MIDI channel 1, i.e. status byte 0x90)
# ---------------------------------------------------------------------------

# Per-channel strip notes — add channel index (0–7) to each base
_NOTE_REC_ARM_BASE = 0
_NOTE_SOLO_BASE = 8
_NOTE_MUTE_BASE = 16
_NOTE_SELECT_BASE = 24

# Transport
_NOTE_REWIND = 91
_NOTE_FAST_FORWARD = 92
_NOTE_STOP = 93
_NOTE_PLAY = 94
_NOTE_RECORD = 95
_NOTE_CYCLE = 86   # Loop / Cycle

# SAVE/UNDO cross-checked 2026-08-08 against the Emagic Logic Control MIDI
# Implementation (v1.0, the same Mackie-licensed protocol family MCU
# belongs to) — "Control Surface Layout and IDs", UTILITIES: SAVE = 0x50,
# UTILITIES: UNDO = 0x51. The previous values (98, 110) didn't match
# anything in that table (98/0x62 = Cursor Left, 110/0x6E = Fader Touch
# Ch. 7) and were likely never verified against a real spec. Not yet
# re-verified live against Studio Pro specifically — do that before
# trusting these fully; Studio Pro's own MCU implementation could still
# deviate from the reference spec.
_NOTE_SAVE = 0x50   # 80
_NOTE_UNDO = 0x51   # 81
# No dedicated Redo button exists anywhere in the reference spec's ID
# table (0x00-0x76) — Logic Control simply doesn't define one. The old
# value (101/0x65) mapped to "Scrub" in that table, not Redo, so it was
# almost certainly wrong too, but there's no known-correct replacement to
# put in its place. Left unverified; transport_redo may just not have a
# working MCU path until this is investigated live.
_NOTE_REDO = 101

# VPot relative CC base (pan encoders) — channels 0–7 → CC 16–23
_CC_VPOT_BASE = 16

# MIDI channel for channel strips: strip N uses pitch-bend channel N+1
# Master fader lives on MIDI channel 9 (0-indexed: 8)
_MIDI_CH_MASTER_FADER = 8

# Maximum 14-bit pitch-bend value
_PB_MAX = 16383

# Bank navigation note numbers
_NOTE_BANK_LEFT = 46
_NOTE_BANK_RIGHT = 47
_NOTE_CHANNEL_LEFT = 48
_NOTE_CHANNEL_RIGHT = 49

# MCU supports 8 banks of 8 channels (0–7)
_MAX_BANK = 7

# Minimum inter-message delay to avoid Studio One dropping rapid bursts
_DEFAULT_MESSAGE_DELAY_S = 0.02


class MidiBridgeError(Exception):
    """Raised when the MIDI bridge cannot open a port or send a message."""


class MidiBridge:
    """Manages a virtual MIDI output port and encodes MCU commands.

    Parameters
    ----------
    port_name:
        Name of the virtual MIDI port to create (must match what Studio One
        is configured to listen on).
    message_delay:
        Seconds to wait between messages when sending press/release pairs.
    """

    def __init__(self, port_name: str = "StudioPro-MCU", message_delay: float = _DEFAULT_MESSAGE_DELAY_S) -> None:
        self._port_name = port_name
        self._message_delay = message_delay
        self._out: rtmidi.MidiOut | None = None
        self._in: rtmidi.MidiIn | None = None
        self._current_bank: int = 0
        # Fader levels start as an optimistic cache (populated when we send
        # commands) but are overwritten with confirmed values whenever the
        # DAW echoes fader position back over the input port — see
        # _on_midi_in(). Mute/solo/rec-arm stay optimistic-only; MCU as
        # implemented here doesn't parse their feedback messages.
        self._fader_levels: dict[str | int, float] = {}
        self._mute_state: dict[int, bool] = {}
        self._solo_state: dict[int, bool] = {}
        self._rec_arm_state: dict[int, bool] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the MIDI output port, plus a paired input port for feedback.

        On macOS and Linux a virtual port is created on the fly. The Windows
        backend of python-rtmidi (WinMM) cannot create virtual ports, so there
        we attach to an already existing loopback port instead — created by
        loopMIDI, LoopBe1 or a comparable tool and named after ``port_name``.
        The input side lets Studio One echo fader positions (and, in future,
        meters) back to us instead of relying solely on what we last sent.
        """
        if self._out is not None:
            return
        try:
            self._out = rtmidi.MidiOut()
            self._in = rtmidi.MidiIn()
            if platform.system() == "Windows":
                self._open_existing_port(self._out, "output")
                self._open_existing_port(self._in, "input")
            else:
                self._out.open_virtual_port(self._port_name)
                self._in.open_virtual_port(self._port_name)
                log.info("Opened virtual MIDI port: %s", self._port_name)
            self._in.set_callback(self._on_midi_in)
        except MidiBridgeError:
            self._out = None
            self._in = None
            raise
        except Exception as exc:
            self._out = None
            self._in = None
            raise MidiBridgeError(f"Failed to open MIDI port '{self._port_name}': {exc}") from exc

        # macOS only: pin a stable uniqueID so a saved Studio One device
        # registration keeps binding to this port across restarts. rtmidi
        # otherwise assigns a fresh random ID each launch. Best-effort.
        if platform.system() == "Darwin":
            try:
                from studio_pro_mcp.coremidi import pin_unique_id

                if pin_unique_id(self._port_name):
                    log.info("Pinned uniqueID for port %s", self._port_name)
            except Exception as exc:  # never block MIDI on this
                log.debug("Could not pin port uniqueID: %s", exc)

    def _open_existing_port(self, port: rtmidi.MidiIn | rtmidi.MidiOut, label: str) -> None:
        """Attach *port* to an existing port whose name contains ``port_name``.

        Windows has no virtual-port support, so the loopback port must already
        exist before the server starts. Works for both ``MidiIn`` and
        ``MidiOut`` — both expose the same ``get_ports``/``open_port`` shape.
        """
        available = port.get_ports()
        wanted = self._port_name.lower()
        for index, name in enumerate(available):
            if wanted in name.lower():
                port.open_port(index)
                log.info("Opened existing MIDI %s port %d: %s", label, index, name)
                return
        raise MidiBridgeError(
            f"No MIDI {label} port matching '{self._port_name}' was found. "
            f"On Windows, create a loopback port with that name first "
            f"(loopMIDI). Available ports: {available or 'none'}"
        )

    def _on_midi_in(self, event: tuple[list[int], float], _data: object = None) -> None:
        """Fold incoming MCU feedback into the fader-level cache.

        Runs on rtmidi's own callback thread, not the asyncio loop — kept to
        a plain dict write, same as everything else this cache does.
        """
        message, _delta_time = event
        if len(message) < 3:
            return
        status, lsb, msb = message[0], message[1], message[2]
        if status & 0xF0 != PITCH_BEND:
            return
        channel = status & 0x0F
        value = (msb << 7) | lsb
        level = value / _PB_MAX * 100.0
        key: str | int = "master" if channel == _MIDI_CH_MASTER_FADER else channel
        if key == "master" or 0 <= channel <= 7:
            self._fader_levels[key] = level

    def close(self) -> None:
        """Close the virtual MIDI ports."""
        if self._in is not None:
            self._in.close_port()
            del self._in
            self._in = None
        if self._out is not None:
            self._out.close_port()
            del self._out
            self._out = None
            log.info("Closed virtual MIDI port: %s", self._port_name)

    def __enter__(self) -> MidiBridge:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def _ensure_open(self) -> Generator[None, None, None]:
        if self._out is None:
            raise MidiBridgeError("MIDI port is not open. Call open() first.")
        yield

    # ------------------------------------------------------------------
    # Low-level send helpers
    # ------------------------------------------------------------------

    def _send(self, message: list[int]) -> None:
        with self._ensure_open():
            log.debug("MIDI → %s", [hex(b) for b in message])
            self._out.send_message(message)  # type: ignore[union-attr]

    def _note_on(self, note: int, velocity: int = 127, channel: int = 0) -> None:
        self._send([NOTE_ON | channel, note, velocity])

    def _note_off(self, note: int, channel: int = 0) -> None:
        self._send([NOTE_ON | channel, note, 0])

    def _button_press(self, note: int, channel: int = 0) -> None:
        """Send a momentary button press (note-on then note-off)."""
        self._note_on(note, 127, channel)
        time.sleep(self._message_delay)
        self._note_off(note, channel)

    def _pitch_bend(self, value: int, channel: int = 0) -> None:
        """Send a 14-bit pitch-bend message on the given MIDI channel."""
        lsb = value & 0x7F
        msb = (value >> 7) & 0x7F
        self._send([PITCH_BEND | channel, lsb, msb])

    def _cc(self, cc: int, value: int, channel: int = 0) -> None:
        self._send([CONTROL_CHANGE | channel, cc, value & 0x7F])

    # ------------------------------------------------------------------
    # Transport commands
    # ------------------------------------------------------------------

    def play(self) -> None:
        self._button_press(_NOTE_PLAY)

    def stop(self) -> None:
        self._button_press(_NOTE_STOP)

    def record(self) -> None:
        self._button_press(_NOTE_RECORD)

    def rewind(self) -> None:
        self._button_press(_NOTE_REWIND)

    def fast_forward(self) -> None:
        self._button_press(_NOTE_FAST_FORWARD)

    def toggle_loop(self) -> None:
        self._button_press(_NOTE_CYCLE)

    def save(self) -> None:
        self._button_press(_NOTE_SAVE)

    def undo(self) -> None:
        self._button_press(_NOTE_UNDO)

    def redo(self) -> None:
        self._button_press(_NOTE_REDO)

    # ------------------------------------------------------------------
    # Mixer commands
    # ------------------------------------------------------------------

    def set_fader(self, channel: int | str, level: float) -> None:
        """Set a fader position.

        Parameters
        ----------
        channel:
            Strip index 0–7, or the string ``"master"``.
        level:
            Linear position 0–100 mapped to pitch-bend 0–16383.
        """
        level = max(0.0, min(100.0, level))
        pb_value = int(level / 100.0 * _PB_MAX)
        if channel == "master":
            midi_ch = _MIDI_CH_MASTER_FADER
        else:
            ch = int(channel)
            if not 0 <= ch <= 7:
                raise ValueError(f"Channel must be 0–7 or 'master', got {channel!r}")
            midi_ch = ch
        self._pitch_bend(pb_value, channel=midi_ch)
        self._fader_levels[channel] = level

    def toggle_mute(self, channel: int) -> None:
        ch = self._validate_strip(channel)
        self._button_press(_NOTE_MUTE_BASE + ch)
        self._mute_state[ch] = not self._mute_state.get(ch, False)

    def toggle_solo(self, channel: int) -> None:
        ch = self._validate_strip(channel)
        self._button_press(_NOTE_SOLO_BASE + ch)
        self._solo_state[ch] = not self._solo_state.get(ch, False)

    def toggle_rec_arm(self, channel: int) -> None:
        ch = self._validate_strip(channel)
        self._button_press(_NOTE_REC_ARM_BASE + ch)
        self._rec_arm_state[ch] = not self._rec_arm_state.get(ch, False)

    def select_channel(self, channel: int) -> None:
        ch = self._validate_strip(channel)
        self._button_press(_NOTE_SELECT_BASE + ch)

    def set_pan(self, channel: int, pan: int) -> None:
        """Adjust pan via a relative VPot encoder message.

        Parameters
        ----------
        pan:
            Signed offset in the range −64 to +63.
            Positive = right, negative = left.
        """
        ch = self._validate_strip(channel)
        pan = max(-64, min(63, pan))
        cc_value = (pan if pan > 0 else 0) if pan >= 0 else 64 + (64 + pan)  # 65–127 = left
        self._cc(_CC_VPOT_BASE + ch, cc_value)

    # ------------------------------------------------------------------
    # Bank navigation
    # ------------------------------------------------------------------

    @property
    def current_bank(self) -> int:
        """0-indexed bank currently displayed on the MCU surface (0 = ch 1–8)."""
        return self._current_bank

    @property
    def channel_offset(self) -> int:
        """Absolute channel offset of the first visible strip (bank × 8)."""
        return self._current_bank * 8

    def bank_left(self) -> bool:
        """Shift one bank left. Returns False (and sends nothing) if already at bank 0."""
        if self._current_bank <= 0:
            return False
        self._button_press(_NOTE_BANK_LEFT)
        self._current_bank -= 1
        return True

    def bank_right(self) -> bool:
        """Shift one bank right. Returns False (and sends nothing) if already at max bank."""
        if self._current_bank >= _MAX_BANK:
            return False
        self._button_press(_NOTE_BANK_RIGHT)
        self._current_bank += 1
        return True

    def channel_left(self) -> None:
        """Nudge the visible window one channel to the left."""
        self._button_press(_NOTE_CHANNEL_LEFT)

    def channel_right(self) -> None:
        """Nudge the visible window one channel to the right."""
        self._button_press(_NOTE_CHANNEL_RIGHT)

    def goto_bank(self, bank: int) -> None:
        """Navigate directly to *bank* (0–7) by sending the required number of bank presses."""
        bank = max(0, min(_MAX_BANK, bank))
        delta = bank - self._current_bank
        if delta == 0:
            return
        note = _NOTE_BANK_RIGHT if delta > 0 else _NOTE_BANK_LEFT
        for _ in range(abs(delta)):
            self._button_press(note)
        self._current_bank = bank

    # ------------------------------------------------------------------
    # State introspection (optimistic cache)
    # ------------------------------------------------------------------

    def get_assumed_state(self) -> dict[str, Any]:
        return {
            "fader_levels": dict(self._fader_levels),
            "mute": dict(self._mute_state),
            "solo": dict(self._solo_state),
            "rec_arm": dict(self._rec_arm_state),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_strip(channel: int) -> int:
        ch = int(channel)
        if not 0 <= ch <= 7:
            raise ValueError(f"Channel strip must be 0–7, got {ch}")
        return ch

    @staticmethod
    def list_available_ports() -> list[str]:
        """Return names of available MIDI output ports on this machine."""
        out = rtmidi.MidiOut()
        return [out.get_port_name(i) for i in range(out.get_port_count())]
