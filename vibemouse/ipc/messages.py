"""IPC message types and LPJSON framing for agent-listener communication."""

from __future__ import annotations

import json
import struct
from typing import Any, Literal

# LPJSON: 4-byte little-endian unsigned length prefix + UTF-8 JSON payload
_LENGTH_PREFIX_SIZE = 4
_MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MiB


def _encode_lpjson(payload: dict[str, Any]) -> bytes:
    """Encode a JSON object as LPJSON frame."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > _MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message size {len(body)} exceeds maximum {_MAX_MESSAGE_SIZE}"
        )
    return struct.pack("<I", len(body)) + body


def _decode_lpjson(data: bytes) -> dict[str, Any]:
    """Decode LPJSON frame to JSON object."""
    if len(data) < _LENGTH_PREFIX_SIZE:
        raise ValueError("Incomplete length prefix")
    length, = struct.unpack("<I", data[:_LENGTH_PREFIX_SIZE])
    if length > _MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Declared message size {length} exceeds maximum {_MAX_MESSAGE_SIZE}"
        )
    if len(data) < _LENGTH_PREFIX_SIZE + length:
        raise ValueError(
            f"Expected {length} bytes payload, got {len(data) - _LENGTH_PREFIX_SIZE}"
        )
    body = data[_LENGTH_PREFIX_SIZE : _LENGTH_PREFIX_SIZE + length]
    return json.loads(body.decode("utf-8"))


def read_lpjson_frame(stream: Any) -> bytes | None:
    """
    Read one LPJSON frame from a stream.
    Returns None on EOF, raises on invalid data.
    """
    prefix = stream.read(_LENGTH_PREFIX_SIZE)
    if len(prefix) == 0:
        return None
    if len(prefix) < _LENGTH_PREFIX_SIZE:
        raise ValueError("Truncated length prefix")
    length, = struct.unpack("<I", prefix)
    if length > _MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Declared message size {length} exceeds maximum {_MAX_MESSAGE_SIZE}"
        )
    body = stream.read(length)
    if len(body) < length:
        raise ValueError(
            f"Expected {length} bytes payload, got {len(body)}"
        )
    return prefix + body


def write_lpjson_frame(stream: Any, payload: dict[str, Any]) -> None:
    """Write one LPJSON frame to a stream."""
    frame = _encode_lpjson(payload)
    stream.write(frame)
    stream.flush()


def binary_reader(stream: Any) -> Any:
    """Return a binary-capable reader for text or binary streams."""
    return getattr(stream, "buffer", stream)


def binary_writer(stream: Any) -> Any:
    """Return a binary-capable writer for text or binary streams."""
    return getattr(stream, "buffer", stream)


# --- Message types ---

EventMessage = dict[str, Any]  # {"type":"event","event":"mouse.side_front.press"}
CommandMessage = dict[str, Any]  # {"type":"command","command":"shutdown"}
Message = EventMessage | CommandMessage


def parse_message(raw: dict[str, Any]) -> Message:
    """Parse a raw JSON object into a typed message."""
    msg_type = raw.get("type")
    if msg_type == "event":
        event = raw.get("event")
        if not isinstance(event, str):
            raise ValueError("event message must have string 'event' field")
        return {"type": "event", "event": event}
    if msg_type == "command":
        command = raw.get("command")
        if not isinstance(command, str):
            raise ValueError("command message must have string 'command' field")
        return {"type": "command", "command": command}
    raise ValueError(f"Unknown message type: {msg_type!r}")


def serialize_message(msg: Message) -> dict[str, Any]:
    """Serialize a message to a JSON-serializable dict."""
    return dict(msg)


def make_event_message(event_name: str) -> EventMessage:
    """Create an event message."""
    return {"type": "event", "event": event_name}


def make_command_message(command_name: str) -> CommandMessage:
    """Create a command message."""
    return {"type": "command", "command": command_name}
