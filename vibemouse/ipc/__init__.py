"""IPC module for agent-listener communication using stdio + LPJSON."""

from vibemouse.ipc.client import IPCClient
from vibemouse.ipc.messages import (
    CommandMessage,
    EventMessage,
    Message,
    binary_reader,
    binary_writer,
    parse_message,
    read_lpjson_frame,
    serialize_message,
    write_lpjson_frame,
)
from vibemouse.ipc.server import AgentCommandServer, IPCServer

__all__ = [
    "AgentCommandServer",
    "binary_reader",
    "binary_writer",
    "CommandMessage",
    "EventMessage",
    "IPCClient",
    "IPCServer",
    "Message",
    "parse_message",
    "read_lpjson_frame",
    "serialize_message",
    "write_lpjson_frame",
]
