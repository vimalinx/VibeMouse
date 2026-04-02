"""IPC servers for stream and loopback command transports."""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Callable

from vibemouse.ipc.messages import (
    _decode_lpjson,
    binary_writer,
    make_command_message,
    parse_message,
    read_lpjson_frame,
    write_lpjson_frame,
)

_LOG = logging.getLogger(__name__)

class IPCServer:
    """
    Server that reads events from a listener child's stdout and optionally
    sends commands to the listener's stdin.
    """

    def __init__(
        self,
        *,
        reader: Any,
        writer: Any | None = None,
        on_event: Callable[[str], None] | None = None,
        on_command: Callable[[str], None] | None = None,
    ) -> None:
        if on_event is None and on_command is None:
            raise ValueError("IPCServer requires on_event or on_command callback")
        self._reader = reader
        self._writer = writer
        self._on_event = on_event
        self._on_command = on_command
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the server loop in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the server loop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)

    def send_command(self, command_name: str) -> None:
        """Send a command to the listener (if writer is configured)."""
        if self._writer is None:
            return
        msg = make_command_message(command_name)
        try:
            write_lpjson_frame(binary_writer(self._writer), msg)
        except Exception as error:
            _LOG.warning("Failed to send command to listener: %s", error)

    def _run(self) -> None:
        while self._running:
            try:
                frame = read_lpjson_frame(self._reader)
                if frame is None:
                    break
                raw = _decode_lpjson(frame)
                msg = parse_message(raw)
                if msg.get("type") == "event":
                    event_name = msg.get("event", "")
                    if self._on_event is not None:
                        self._on_event(event_name)
                elif msg.get("type") == "command":
                    command_name = msg.get("command", "")
                    if self._on_command is not None:
                        self._on_command(command_name)
            except Exception as error:
                if self._running:
                    _LOG.exception("IPC server error: %s", error)
                break
        self._running = False


class AgentCommandServer:
    """Loopback-only command server for external clients driving the agent."""

    def __init__(
        self,
        *,
        on_command: Callable[[str], None],
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self._on_command = on_command
        self._host = host
        self._requested_port = port
        self._listener: socket.socket | None = None
        self._port = 0
        self._running = False
        self._accept_thread: threading.Thread | None = None
        self._client_threads: set[threading.Thread] = set()
        self._client_connections: set[socket.socket] = set()
        self._clients_lock = threading.Lock()

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        if self._listener is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self._host, self._requested_port))
        listener.listen()
        listener.settimeout(0.2)
        self._listener = listener
        self._port = int(listener.getsockname()[1])
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        self._running = False
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        with self._clients_lock:
            connections = list(self._client_connections)
        for conn in connections:
            try:
                conn.close()
            except OSError:
                pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2)
            self._accept_thread = None
        with self._clients_lock:
            client_threads = list(self._client_threads)
        for thread in client_threads:
            thread.join(timeout=2)
        with self._clients_lock:
            self._client_threads.clear()
            self._client_connections.clear()
        self._port = 0

    def _accept_loop(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while self._running:
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError as error:
                if self._running:
                    _LOG.warning("Command server accept failed: %s", error)
                break
            with self._clients_lock:
                self._client_connections.add(conn)
            thread = threading.Thread(
                target=self._serve_client,
                args=(conn,),
                daemon=True,
            )
            with self._clients_lock:
                self._client_threads.add(thread)
            thread.start()
        self._running = False

    def _serve_client(self, conn: socket.socket) -> None:
        stream = conn.makefile("rwb")
        current = threading.current_thread()
        try:
            while self._running:
                frame = read_lpjson_frame(stream)
                if frame is None:
                    break
                raw = _decode_lpjson(frame)
                msg = parse_message(raw)
                if msg.get("type") != "command":
                    _LOG.debug("Ignoring non-command message on command server")
                    continue
                command_name = msg.get("command", "")
                self._on_command(command_name)
        except Exception as error:
            if self._running:
                _LOG.exception("Command server client error: %s", error)
        finally:
            try:
                stream.close()
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
            with self._clients_lock:
                self._client_connections.discard(conn)
                self._client_threads.discard(current)
