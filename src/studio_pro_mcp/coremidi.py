"""Minimal CoreMIDI access (macOS) for enumerating endpoints and pinning a
stable uniqueID on our virtual port.

Studio One identifies a MIDI port in ``MusicDevices.settings`` as
``<Capture|Output>/<uniqueID-as-hex>::<DisplayName>``. rtmidi assigns a *random*
uniqueID to a virtual port on every launch, which would invalidate a saved
device registration. To make the registration durable we pin our virtual
port's uniqueID to a fixed constant (:data:`MCP_PORT_UNIQUE_ID`) right after
opening it, so Studio One re-binds to the same port every time.

This module is macOS-only; on other platforms the functions raise or no-op.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import platform

# Fixed uniqueID for the "StudioPro-MCU" virtual port ("S1MC" as a 32-bit int,
# kept from the port's original name so the pinned ID stays stable across
# the rename).
# Positive 32-bit, so Studio One writes it as plain hex "53314D43".
MCP_PORT_UNIQUE_ID = 0x53314D43

_IS_MAC = platform.system() == "Darwin"
_CF_ENCODING_UTF8 = 0x08000100


class CoreMIDIError(Exception):
    """CoreMIDI access failed."""


class _CoreMIDI:
    """Lazily-loaded ctypes bindings for the handful of CoreMIDI calls we need."""

    def __init__(self) -> None:
        cm_path = ctypes.util.find_library("CoreMIDI")
        cf_path = ctypes.util.find_library("CoreFoundation")
        if not cm_path or not cf_path:
            raise CoreMIDIError("CoreMIDI/CoreFoundation not found (macOS only).")
        self.cm = ctypes.CDLL(cm_path)
        self.cf = ctypes.CDLL(cf_path)

        self.kUID = ctypes.c_void_p.in_dll(self.cm, "kMIDIPropertyUniqueID")
        self.kDisplayName = ctypes.c_void_p.in_dll(self.cm, "kMIDIPropertyDisplayName")
        self.kName = ctypes.c_void_p.in_dll(self.cm, "kMIDIPropertyName")

        self.cm.MIDIGetNumberOfSources.restype = ctypes.c_ulong
        self.cm.MIDIGetNumberOfDestinations.restype = ctypes.c_ulong
        self.cm.MIDIGetSource.restype = ctypes.c_uint32
        self.cm.MIDIGetSource.argtypes = [ctypes.c_ulong]
        self.cm.MIDIGetDestination.restype = ctypes.c_uint32
        self.cm.MIDIGetDestination.argtypes = [ctypes.c_ulong]
        self.cm.MIDIObjectGetIntegerProperty.restype = ctypes.c_int32
        self.cm.MIDIObjectGetIntegerProperty.argtypes = [
            ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32)
        ]
        self.cm.MIDIObjectSetIntegerProperty.restype = ctypes.c_int32
        self.cm.MIDIObjectSetIntegerProperty.argtypes = [
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int32
        ]
        self.cm.MIDIObjectGetStringProperty.restype = ctypes.c_int32
        self.cm.MIDIObjectGetStringProperty.argtypes = [
            ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        ]
        self.cf.CFStringGetCString.restype = ctypes.c_bool
        self.cf.CFStringGetCString.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32
        ]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]

    def _string_prop(self, obj: int, prop: ctypes.c_void_p) -> str | None:
        out = ctypes.c_void_p()
        if self.cm.MIDIObjectGetStringProperty(obj, prop, ctypes.byref(out)) != 0 or not out.value:
            return None
        buf = ctypes.create_string_buffer(512)
        ok = self.cf.CFStringGetCString(out, buf, 512, _CF_ENCODING_UTF8)
        self.cf.CFRelease(out)
        return buf.value.decode("utf-8") if ok else None

    def _uid(self, obj: int) -> int:
        val = ctypes.c_int32(0)
        self.cm.MIDIObjectGetIntegerProperty(obj, self.kUID, ctypes.byref(val))
        return val.value

    def name_of(self, obj: int) -> str | None:
        return self._string_prop(obj, self.kDisplayName) or self._string_prop(obj, self.kName)


_singleton: _CoreMIDI | None = None


def _midi() -> _CoreMIDI:
    global _singleton
    if not _IS_MAC:
        raise CoreMIDIError("CoreMIDI is only available on macOS.")
    if _singleton is None:
        _singleton = _CoreMIDI()
    return _singleton


def s1_uid_hex(uid: int) -> str:
    """Format a CoreMIDI uniqueID the way Studio One writes it in port IDs.

    Negative (SInt32) IDs are sign-extended to 16 hex digits; positive IDs use
    their natural hex form.
    """
    if uid < 0:
        return f"{uid & 0xFFFFFFFFFFFFFFFF:X}"
    return f"{uid:X}"


def studio_one_port_id(direction: str, uid: int, name: str) -> str:
    """Build a Studio One port ID: ``Capture/<hex>::<name>`` or ``Output/<hex>::<name>``."""
    prefix = {"source": "Capture", "destination": "Output"}[direction]
    return f"{prefix}/{s1_uid_hex(uid)}::{name}"


def list_endpoints(direction: str) -> list[tuple[str, int]]:
    """Return ``[(display_name, uniqueID), ...]`` for sources or destinations."""
    m = _midi()
    if direction == "source":
        n, get = m.cm.MIDIGetNumberOfSources(), m.cm.MIDIGetSource
    elif direction == "destination":
        n, get = m.cm.MIDIGetNumberOfDestinations(), m.cm.MIDIGetDestination
    else:
        raise ValueError(f"direction must be 'source' or 'destination', got {direction!r}")
    out: list[tuple[str, int]] = []
    for i in range(n):
        ep = get(i)
        name = m.name_of(ep)
        if name is not None:
            out.append((name, m._uid(ep)))
    return out


def find_endpoint(direction: str, name: str) -> int:
    """Return the CoreMIDI endpoint ref whose display name == *name*, or 0."""
    m = _midi()
    if direction == "source":
        n, get = m.cm.MIDIGetNumberOfSources(), m.cm.MIDIGetSource
    else:
        n, get = m.cm.MIDIGetNumberOfDestinations(), m.cm.MIDIGetDestination
    for i in range(n):
        ep = get(i)
        if m.name_of(ep) == name:
            return int(ep)
    return 0


def pin_unique_id(name: str, uid: int = MCP_PORT_UNIQUE_ID) -> bool:
    """Pin the source endpoint named *name* to a fixed uniqueID.

    Returns True on success. Best-effort: returns False if the endpoint isn't
    found or the ID is already taken by another endpoint. macOS only.
    """
    if not _IS_MAC:
        return False
    try:
        m = _midi()
    except CoreMIDIError:
        return False
    ep = find_endpoint("source", name)
    if not ep:
        return False
    status = m.cm.MIDIObjectSetIntegerProperty(ep, m.kUID, uid)
    return bool(status == 0)
