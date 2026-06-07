"""UCNET wire-format encoding and decoding.

Frame layout (all integers little-endian):
  [0:4]  payload_length  uint32  — byte count of everything after this field
  [4:6]  message_type    uint16  — see MessageType enum
  [6:]   payload         bytes   — message_type-specific (length = payload_length - 2)

Parameter path encoding: uint16 length prefix + UTF-8 bytes.
Value encoding varies by message type (see _encode_* / _decode_* helpers).

These are PRELIMINARY specifications inferred from packet captures.
Path names and value encodings may differ in the shipping binary.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class MessageType(IntEnum):
    HELLO = 0x0001           # Handshake — client introduces itself
    PARAM_FLOAT = 0x0010     # Parameter update: path + float32
    PARAM_INT = 0x0011       # Parameter update: path + int32
    PARAM_STRING = 0x0012    # Parameter update: path + utf-8 string
    SUBSCRIBE = 0x0020       # Subscribe to a parameter subtree
    TRANSPORT_CMD = 0x0030   # Transport command (play/stop/record …)
    SNAPSHOT = 0x0040        # Full state snapshot chunk
    KEEPALIVE = 0x00FF       # Ping / heartbeat (empty payload)


# Type alias for the three parameter value kinds
ParameterValue = float | int | str

# Struct formats (little-endian)
_FMT_FRAME_HEADER = "<IH"   # uint32 payload_len, uint16 msg_type
_FMT_FLOAT32 = "<f"
_FMT_INT32 = "<i"
_FMT_UINT16 = "<H"

_FRAME_HEADER_SIZE = struct.calcsize(_FMT_FRAME_HEADER)  # 6 bytes


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _encode_str(value: str) -> bytes:
    """Encode a string as uint16-prefixed UTF-8."""
    encoded = value.encode()
    return struct.pack(_FMT_UINT16, len(encoded)) + encoded


def _encode_path(path: str) -> bytes:
    return _encode_str(path)


def _build_frame(msg_type: MessageType, payload: bytes) -> bytes:
    """Wrap *payload* in a UCNET frame header."""
    payload_length = len(payload) + 2  # +2 for the msg_type field
    header = struct.pack(_FMT_FRAME_HEADER, payload_length, int(msg_type))
    return header + payload


# ---------------------------------------------------------------------------
# Public encoders — one per message type
# ---------------------------------------------------------------------------

def encode_hello(client_name: str, client_version: str) -> bytes:
    payload = _encode_str(client_name) + _encode_str(client_version)
    return _build_frame(MessageType.HELLO, payload)


def encode_keepalive() -> bytes:
    return _build_frame(MessageType.KEEPALIVE, b"")


def encode_subscribe(path: str) -> bytes:
    return _build_frame(MessageType.SUBSCRIBE, _encode_path(path))


def encode_param_float(path: str, value: float) -> bytes:
    payload = _encode_path(path) + struct.pack(_FMT_FLOAT32, value)
    return _build_frame(MessageType.PARAM_FLOAT, payload)


def encode_param_int(path: str, value: int) -> bytes:
    payload = _encode_path(path) + struct.pack(_FMT_INT32, value)
    return _build_frame(MessageType.PARAM_INT, payload)


def encode_param_string(path: str, value: str) -> bytes:
    payload = _encode_path(path) + _encode_str(value)
    return _build_frame(MessageType.PARAM_STRING, payload)


def encode_set_parameter(path: str, value: ParameterValue) -> bytes:
    """Encode a parameter write, choosing the correct message type automatically."""
    if isinstance(value, float):
        return encode_param_float(path, value)
    if isinstance(value, int):
        return encode_param_int(path, value)
    if isinstance(value, str):
        return encode_param_string(path, value)
    raise TypeError(f"Unsupported parameter value type: {type(value)}")


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    msg_type: MessageType
    payload: bytes

    @property
    def is_keepalive(self) -> bool:
        return self.msg_type == MessageType.KEEPALIVE


@dataclass
class ParameterUpdate:
    path: str
    value: ParameterValue
    msg_type: MessageType


def decode_frame_header(data: bytes) -> tuple[int, MessageType]:
    """Parse a 6-byte frame header; return (payload_length, msg_type)."""
    if len(data) < _FRAME_HEADER_SIZE:
        raise ValueError(f"Header too short: {len(data)} < {_FRAME_HEADER_SIZE}")
    payload_length, raw_type = struct.unpack(_FMT_FRAME_HEADER, data[:_FRAME_HEADER_SIZE])
    try:
        msg_type = MessageType(raw_type)
    except ValueError:
        msg_type = MessageType(raw_type)  # leave as-is for forward compat
    return payload_length, msg_type


def _decode_str(data: bytes, offset: int) -> tuple[str, int]:
    """Decode a uint16-prefixed UTF-8 string; return (string, new_offset)."""
    (length,) = struct.unpack_from(_FMT_UINT16, data, offset)
    offset += 2
    value = data[offset : offset + length].decode()
    return value, offset + length


def decode_parameter_update(frame: Frame) -> ParameterUpdate:
    """Decode a PARAM_FLOAT, PARAM_INT, or PARAM_STRING frame."""
    if frame.msg_type not in (MessageType.PARAM_FLOAT, MessageType.PARAM_INT, MessageType.PARAM_STRING):
        raise ValueError(f"Frame type {frame.msg_type!r} is not a parameter update")

    payload = frame.payload
    path, offset = _decode_str(payload, 0)

    match frame.msg_type:
        case MessageType.PARAM_FLOAT:
            (value,) = struct.unpack_from(_FMT_FLOAT32, payload, offset)
            return ParameterUpdate(path=path, value=float(value), msg_type=frame.msg_type)
        case MessageType.PARAM_INT:
            (value,) = struct.unpack_from(_FMT_INT32, payload, offset)
            return ParameterUpdate(path=path, value=int(value), msg_type=frame.msg_type)
        case MessageType.PARAM_STRING:
            string_value, _ = _decode_str(payload, offset)
            return ParameterUpdate(path=path, value=string_value, msg_type=frame.msg_type)
        case _:  # unreachable — guard above ensures only valid types reach here
            raise AssertionError("unreachable")


FRAME_HEADER_SIZE = _FRAME_HEADER_SIZE
