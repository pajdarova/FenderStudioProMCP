"""Tests for UCNET frame encoding and decoding (no network required)."""

from __future__ import annotations

import struct

import pytest

from studio_one_mcp.ucnet.protocol import (
    FRAME_HEADER_SIZE,
    Frame,
    MessageType,
    decode_frame_header,
    decode_parameter_update,
    encode_hello,
    encode_keepalive,
    encode_param_float,
    encode_param_int,
    encode_param_string,
    encode_set_parameter,
    encode_subscribe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frame(data: bytes) -> Frame:
    payload_length, msg_type = decode_frame_header(data[:FRAME_HEADER_SIZE])
    body_length = payload_length - 2
    payload = data[FRAME_HEADER_SIZE : FRAME_HEADER_SIZE + body_length]
    return Frame(msg_type=msg_type, payload=payload)


def _decode_str_at(data: bytes, offset: int) -> tuple[str, int]:
    (length,) = struct.unpack_from("<H", data, offset)
    s = data[offset + 2 : offset + 2 + length].decode()
    return s, offset + 2 + length


# ---------------------------------------------------------------------------
# Frame header
# ---------------------------------------------------------------------------

class TestFrameHeader:
    def test_keepalive_has_correct_type(self):
        frame = _parse_frame(encode_keepalive())
        assert frame.msg_type == MessageType.KEEPALIVE

    def test_keepalive_payload_empty(self):
        frame = _parse_frame(encode_keepalive())
        assert frame.payload == b""

    def test_keepalive_is_keepalive(self):
        frame = _parse_frame(encode_keepalive())
        assert frame.is_keepalive

    def test_header_size_is_six(self):
        assert FRAME_HEADER_SIZE == 6

    def test_payload_length_field_covers_msg_type(self):
        data = encode_keepalive()
        (payload_length,) = struct.unpack_from("<I", data, 0)
        # payload_length = 2 (msg_type) + 0 (empty payload)
        assert payload_length == 2

    def test_decode_header_too_short_raises(self):
        with pytest.raises(ValueError):
            decode_frame_header(b"\x00\x00")


# ---------------------------------------------------------------------------
# Hello
# ---------------------------------------------------------------------------

class TestHello:
    def test_hello_frame_type(self):
        frame = _parse_frame(encode_hello("MyClient", "1.0"))
        assert frame.msg_type == MessageType.HELLO

    def test_hello_contains_client_name(self):
        frame = _parse_frame(encode_hello("MyClient", "1.0"))
        name, _ = _decode_str_at(frame.payload, 0)
        assert name == "MyClient"

    def test_hello_contains_version(self):
        frame = _parse_frame(encode_hello("MyClient", "1.0.0"))
        _, offset = _decode_str_at(frame.payload, 0)
        version, _ = _decode_str_at(frame.payload, offset)
        assert version == "1.0.0"


# ---------------------------------------------------------------------------
# Subscribe
# ---------------------------------------------------------------------------

class TestSubscribe:
    def test_subscribe_frame_type(self):
        frame = _parse_frame(encode_subscribe("/transport"))
        assert frame.msg_type == MessageType.SUBSCRIBE

    def test_subscribe_encodes_path(self):
        frame = _parse_frame(encode_subscribe("/transport"))
        path, _ = _decode_str_at(frame.payload, 0)
        assert path == "/transport"

    def test_subscribe_mixer_path(self):
        frame = _parse_frame(encode_subscribe("/mixer/channel[0]"))
        path, _ = _decode_str_at(frame.payload, 0)
        assert path == "/mixer/channel[0]"


# ---------------------------------------------------------------------------
# Parameter encoding
# ---------------------------------------------------------------------------

class TestParamFloat:
    def test_frame_type(self):
        frame = _parse_frame(encode_param_float("/transport/tempo", 120.0))
        assert frame.msg_type == MessageType.PARAM_FLOAT

    def test_round_trip(self):
        frame = _parse_frame(encode_param_float("/transport/tempo", 120.0))
        update = decode_parameter_update(frame)
        assert update.path == "/transport/tempo"
        assert isinstance(update.value, float)
        assert abs(update.value - 120.0) < 1e-4

    def test_zero_value(self):
        frame = _parse_frame(encode_param_float("/some/param", 0.0))
        update = decode_parameter_update(frame)
        assert update.value == pytest.approx(0.0)

    def test_negative_value(self):
        frame = _parse_frame(encode_param_float("/db", -12.5))
        update = decode_parameter_update(frame)
        assert update.value == pytest.approx(-12.5, abs=1e-4)


class TestParamInt:
    def test_frame_type(self):
        frame = _parse_frame(encode_param_int("/transport/isPlaying", 1))
        assert frame.msg_type == MessageType.PARAM_INT

    def test_round_trip_true(self):
        frame = _parse_frame(encode_param_int("/transport/isPlaying", 1))
        update = decode_parameter_update(frame)
        assert update.path == "/transport/isPlaying"
        assert update.value == 1

    def test_round_trip_false(self):
        frame = _parse_frame(encode_param_int("/transport/isPlaying", 0))
        update = decode_parameter_update(frame)
        assert update.value == 0

    def test_negative_int(self):
        frame = _parse_frame(encode_param_int("/some/signed", -42))
        update = decode_parameter_update(frame)
        assert update.value == -42


class TestParamString:
    def test_frame_type(self):
        frame = _parse_frame(encode_param_string("/mixer/channel[0]/name", "Kick"))
        assert frame.msg_type == MessageType.PARAM_STRING

    def test_round_trip(self):
        frame = _parse_frame(encode_param_string("/mixer/channel[0]/name", "Lead Vocal"))
        update = decode_parameter_update(frame)
        assert update.path == "/mixer/channel[0]/name"
        assert update.value == "Lead Vocal"

    def test_unicode_string(self):
        frame = _parse_frame(encode_param_string("/name", "Guitare électrique"))
        update = decode_parameter_update(frame)
        assert update.value == "Guitare électrique"

    def test_empty_string(self):
        frame = _parse_frame(encode_param_string("/name", ""))
        update = decode_parameter_update(frame)
        assert update.value == ""


# ---------------------------------------------------------------------------
# encode_set_parameter dispatcher
# ---------------------------------------------------------------------------

class TestEncodeSetParameter:
    def test_float_dispatches_to_param_float(self):
        frame = _parse_frame(encode_set_parameter("/tempo", 120.0))
        assert frame.msg_type == MessageType.PARAM_FLOAT

    def test_int_dispatches_to_param_int(self):
        frame = _parse_frame(encode_set_parameter("/mute", 1))
        assert frame.msg_type == MessageType.PARAM_INT

    def test_str_dispatches_to_param_string(self):
        frame = _parse_frame(encode_set_parameter("/name", "Bass"))
        assert frame.msg_type == MessageType.PARAM_STRING

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            encode_set_parameter("/x", [1, 2, 3])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Decoding errors
# ---------------------------------------------------------------------------

class TestDecodeErrors:
    def test_wrong_msg_type_raises(self):
        frame = Frame(msg_type=MessageType.KEEPALIVE, payload=b"")
        with pytest.raises(ValueError, match="not a parameter update"):
            decode_parameter_update(frame)

    def test_truncated_payload_raises(self):
        frame = Frame(msg_type=MessageType.PARAM_FLOAT, payload=b"\x04\x00/foo")
        with pytest.raises(struct.error):
            decode_parameter_update(frame)
