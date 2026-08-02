"""Tests for IPC client-server round-trip over pipes."""

from __future__ import annotations

import io
import json
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import pytest

from vibemouse.ipc.client import IPCClient
from vibemouse.ipc.messages import make_command_message, write_lpjson_frame
from vibemouse.ipc.server import AgentCommandServer, IPCServer, default_command_endpoint


def test_ipc_client_send_event() -> None:
    """IPCClient.send_event writes valid LPJSON to stdout (simulating pipe)."""
    stdout_buf = io.BytesIO()
    stdin_buf = io.BytesIO()
    client = IPCClient(stdin=stdin_buf, stdout=stdout_buf)
    client.send_event("hotkey.record_toggle")
    data = stdout_buf.getvalue()
    assert len(data) >= 4
    length, = struct.unpack("<I", data[:4])
    assert length == len(data) - 4
    payload = json.loads(data[4:].decode("utf-8"))
    assert payload == {"type": "event", "event": "hotkey.record_toggle"}


def test_ipc_server_receives_event() -> None:
    """IPCServer receives event from reader and calls on_event."""
    payload = {"type": "event", "event": "mouse.side_rear.press"}
    body = json.dumps(payload).encode("utf-8")
    frame = struct.pack("<I", len(body)) + body
    reader = io.BytesIO(frame)
    writer = io.BytesIO()
    received: list[str] = []
    server = IPCServer(
        reader=reader,
        writer=writer,
        on_event=lambda e: received.append(e),
    )
    server.start()
    time.sleep(0.1)
    server.stop()
    assert received == ["mouse.side_rear.press"]


def test_ipc_server_send_command() -> None:
    """IPCServer.send_command writes valid LPJSON to writer."""
    reader = io.BytesIO()  # empty, no events
    writer = io.BytesIO()
    server = IPCServer(
        reader=reader,
        writer=writer,
        on_event=lambda e: None,
    )
    server.send_command("shutdown")
    data = writer.getvalue()
    assert len(data) >= 4
    length, = struct.unpack("<I", data[:4])
    assert length == len(data) - 4
    payload = json.loads(data[4:].decode("utf-8"))
    assert payload == {"type": "command", "command": "shutdown"}


def test_ipc_server_receives_command_when_handler_is_configured() -> None:
    payload = {"type": "command", "command": "reload_config"}
    body = json.dumps(payload).encode("utf-8")
    frame = struct.pack("<I", len(body)) + body
    reader = io.BytesIO(frame)
    received: list[str] = []
    server = IPCServer(reader=reader, on_command=lambda cmd: received.append(cmd))
    server.start()
    time.sleep(0.1)
    server.stop()
    assert received == ["reload_config"]


def test_default_command_endpoint_uses_stable_local_address() -> None:
    endpoint = default_command_endpoint()
    if sys.platform == "win32":
        assert endpoint == r"\\.\pipe\vibemouse"
    else:
        assert Path(endpoint).name == "vibemouse.sock"


def test_agent_command_server_accepts_local_command() -> None:
    if sys.platform == "win32":
        pytest.skip("End-to-end named pipe client coverage is not implemented in this test")
    received: list[str] = []
    ready = threading.Event()

    def on_command(command_name: str) -> None:
        received.append(command_name)
        ready.set()

    server = AgentCommandServer(on_command=on_command)
    server.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(2)
            conn.connect(server.endpoint)
            stream = conn.makefile("rwb")
            write_lpjson_frame(stream, make_command_message("shutdown"))
            stream.close()
        assert ready.wait(timeout=2)
        assert received == ["shutdown"]
    finally:
        server.stop()
