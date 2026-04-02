"""Tests for IPC message types and LPJSON framing."""

from __future__ import annotations

import io
import json
import struct

import pytest

from vibemouse.ipc.messages import (
    _decode_lpjson,
    _encode_lpjson,
    make_command_message,
    make_event_message,
    parse_message,
    read_lpjson_frame,
    serialize_message,
    write_lpjson_frame,
)


def test_make_event_message() -> None:
    msg = make_event_message("mouse.side_front.press")
    assert msg == {"type": "event", "event": "mouse.side_front.press"}


def test_make_command_message() -> None:
    msg = make_command_message("shutdown")
    assert msg == {"type": "command", "command": "shutdown"}


def test_parse_event_message() -> None:
    raw = {"type": "event", "event": "hotkey.record_toggle"}
    msg = parse_message(raw)
    assert msg["type"] == "event"
    assert msg["event"] == "hotkey.record_toggle"


def test_parse_command_message() -> None:
    raw = {"type": "command", "command": "reload_config"}
    msg = parse_message(raw)
    assert msg["type"] == "command"
    assert msg["command"] == "reload_config"


def test_parse_message_invalid_type() -> None:
    with pytest.raises(ValueError, match="Unknown message type"):
        parse_message({"type": "unknown"})


def test_parse_message_event_missing_field() -> None:
    with pytest.raises(ValueError, match="event message must have"):
        parse_message({"type": "event"})


def test_serialize_message() -> None:
    msg = make_event_message("gesture.left")
    assert serialize_message(msg) == {"type": "event", "event": "gesture.left"}


def test_encode_decode_lpjson() -> None:
    payload = {"type": "event", "event": "mouse.side_rear.press"}
    frame = _encode_lpjson(payload)
    assert len(frame) >= 4
    length, = struct.unpack("<I", frame[:4])
    assert length == len(frame) - 4
    decoded = _decode_lpjson(frame)
    assert decoded == payload


def test_read_write_lpjson_frame() -> None:
    stream = io.BytesIO()
    payload = {"type": "command", "command": "toggle_recording"}
    write_lpjson_frame(stream, payload)
    stream.seek(0)
    frame = read_lpjson_frame(stream)
    assert frame is not None
    decoded = _decode_lpjson(frame)
    assert decoded == payload


def test_read_lpjson_frame_eof() -> None:
    stream = io.BytesIO()
    frame = read_lpjson_frame(stream)
    assert frame is None


def test_encode_lpjson_max_size_exceeded() -> None:
    large = {"x": "a" * (1024 * 1024 + 1)}
    with pytest.raises(ValueError, match="exceeds maximum"):
        _encode_lpjson(large)
