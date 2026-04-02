"""IPC client for connecting to agent via stdio or other binary streams."""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable

from vibemouse.ipc.messages import (
    _decode_lpjson,
    binary_reader,
    binary_writer,
    make_command_message,
    make_event_message,
    parse_message,
    read_lpjson_frame,
    write_lpjson_frame,
)

_LOG = logging.getLogger(__name__)

class IPCClient:
    """
    Client that sends events to agent and receives commands from agent
    over stdio using LPJSON framing.
    """

    def __init__(
        self,
        *,
        stdin: Any = None,
        stdout: Any = None,
        on_command: Callable[[str], None] | None = None,
    ) -> None:
        self._stdin = stdin if stdin is not None else sys.stdin
        self._stdout = stdout if stdout is not None else sys.stdout
        self._on_command = on_command
        self._running = False

    def send_event(self, event_name: str) -> None:
        """Send an event message to the agent."""
        msg = make_event_message(event_name)
        write_lpjson_frame(binary_writer(self._stdout), msg)

    def send_command(self, command_name: str) -> None:
        """Send a command message to the connected peer."""
        msg = make_command_message(command_name)
        write_lpjson_frame(binary_writer(self._stdout), msg)

    def run(self) -> None:
        """Run the client loop: read commands from stdin, dispatch to on_command."""
        self._running = True
        reader = binary_reader(self._stdin)
        while self._running:
            try:
                frame = read_lpjson_frame(reader)
                if frame is None:
                    break
                raw = _decode_lpjson(frame)
                msg = parse_message(raw)
                if msg.get("type") == "command":
                    cmd = msg.get("command", "")
                    if self._on_command is not None:
                        self._on_command(cmd)
            except Exception as error:
                _LOG.exception("IPC client error: %s", error)
                break
        self._running = False

    def stop(self) -> None:
        """Stop the client loop."""
        self._running = False
