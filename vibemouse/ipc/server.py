"""IPC servers for stream and local command transports."""

from __future__ import annotations

import logging
import os
import socket
import sys
import tempfile
import threading
from typing import Any, Callable, Protocol

from vibemouse.ipc.messages import (
    _decode_lpjson,
    binary_writer,
    make_command_message,
    parse_message,
    read_lpjson_frame,
    write_lpjson_frame,
)

_LOG = logging.getLogger(__name__)


class _ReadableStream(Protocol):
    def read(self, size: int) -> bytes: ...

    def close(self) -> None: ...


def default_command_endpoint() -> str:
    """Return the stable local command endpoint for the current platform."""
    if sys.platform == "win32":
        return r"\\.\pipe\vibemouse"
    runtime_dir = os.getenv("XDG_RUNTIME_DIR", tempfile.gettempdir())
    return os.path.join(runtime_dir, "vibemouse.sock")


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
    """Stable local command server for external clients driving the agent."""

    def __init__(
        self,
        *,
        on_command: Callable[[str], None],
        endpoint: str | None = None,
    ) -> None:
        self._on_command = on_command
        self._endpoint = endpoint or default_command_endpoint()
        self._listener: socket.socket | int | None = None
        self._running = False
        self._accept_thread: threading.Thread | None = None
        self._client_threads: set[threading.Thread] = set()
        self._client_connections: set[Any] = set()
        self._clients_lock = threading.Lock()

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def port(self) -> int:
        # Backward-compatible attribute for older callers; stable endpoints do not use a port.
        return 0

    def start(self) -> None:
        if self._listener is not None:
            return
        self._running = True
        if sys.platform == "win32":
            self._accept_thread = threading.Thread(
                target=self._accept_loop_pipe,
                daemon=True,
            )
            self._accept_thread.start()
            return

        endpoint_dir = os.path.dirname(self._endpoint)
        if endpoint_dir:
            os.makedirs(endpoint_dir, exist_ok=True)
        try:
            os.unlink(self._endpoint)
        except FileNotFoundError:
            pass
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self._endpoint)
        listener.listen()
        listener.settimeout(0.2)
        self._listener = listener
        self._accept_thread = threading.Thread(target=self._accept_loop_socket, daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        self._running = False
        listener = self._listener
        self._listener = None
        if sys.platform == "win32":
            if isinstance(listener, int):
                _close_pipe_handle(listener)
        elif isinstance(listener, socket.socket):
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
            except Exception:
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
        if sys.platform != "win32":
            try:
                os.unlink(self._endpoint)
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def _accept_loop_socket(self) -> None:
        listener = self._listener
        if not isinstance(listener, socket.socket):
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
                target=self._serve_stream,
                args=(conn.makefile("rwb"), conn),
                daemon=True,
            )
            with self._clients_lock:
                self._client_threads.add(thread)
            thread.start()
        self._running = False

    def _accept_loop_pipe(self) -> None:
        while self._running:
            handle = _create_named_pipe(self._endpoint)
            self._listener = handle
            if handle is None:
                break
            if not _connect_named_pipe(handle):
                _close_pipe_handle(handle)
                if self._running:
                    _LOG.warning("Command server named pipe connect failed")
                continue
            stream = _NamedPipeStream(handle)
            with self._clients_lock:
                self._client_connections.add(stream)
            thread = threading.Thread(
                target=self._serve_stream,
                args=(stream, stream),
                daemon=True,
            )
            with self._clients_lock:
                self._client_threads.add(thread)
            thread.start()
        self._running = False

    def _serve_stream(self, stream: _ReadableStream, connection: Any) -> None:
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
            except Exception:
                pass
            try:
                connection.close()
            except OSError:
                pass
            except Exception:
                pass
            with self._clients_lock:
                self._client_connections.discard(connection)
                self._client_threads.discard(current)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _ERROR_BROKEN_PIPE = 109
    _ERROR_PIPE_CONNECTED = 535
    _PIPE_ACCESS_INBOUND = 0x00000001
    _PIPE_TYPE_BYTE = 0x00000000
    _PIPE_READMODE_BYTE = 0x00000000
    _PIPE_WAIT = 0x00000000
    _PIPE_UNLIMITED_INSTANCES = 255

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    _kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    _kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    _kernel32.ConnectNamedPipe.restype = wintypes.BOOL
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL
    _kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
    _kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


    def _create_named_pipe(endpoint: str) -> int | None:
        handle = _kernel32.CreateNamedPipeW(
            endpoint,
            _PIPE_ACCESS_INBOUND,
            _PIPE_TYPE_BYTE | _PIPE_READMODE_BYTE | _PIPE_WAIT,
            _PIPE_UNLIMITED_INSTANCES,
            65536,
            65536,
            0,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            _LOG.warning("Failed to create named pipe %s: winerror=%s", endpoint, error)
            return None
        return int(handle)


    def _connect_named_pipe(handle: int) -> bool:
        ok = bool(_kernel32.ConnectNamedPipe(handle, None))
        if ok:
            return True
        error = ctypes.get_last_error()
        return error == _ERROR_PIPE_CONNECTED


    def _close_pipe_handle(handle: int) -> None:
        try:
            _kernel32.DisconnectNamedPipe(handle)
        except Exception:
            pass
        _kernel32.CloseHandle(handle)


    class _NamedPipeStream:
        def __init__(self, handle: int) -> None:
            self._handle = handle
            self._closed = False

        def read(self, size: int) -> bytes:
            if self._closed:
                return b""
            chunks: list[bytes] = []
            remaining = size
            while remaining > 0:
                buffer = ctypes.create_string_buffer(remaining)
                read = wintypes.DWORD(0)
                ok = bool(
                    _kernel32.ReadFile(
                        self._handle,
                        buffer,
                        remaining,
                        ctypes.byref(read),
                        None,
                    )
                )
                if not ok:
                    error = ctypes.get_last_error()
                    if error == _ERROR_BROKEN_PIPE:
                        if not chunks:
                            return b""
                        raise ValueError("Pipe closed mid-frame")
                    raise OSError(f"Named pipe read failed: winerror={error}")
                if read.value == 0:
                    return b"" if not chunks else b"".join(chunks)
                chunk = buffer.raw[: read.value]
                chunks.append(chunk)
                remaining -= read.value
            return b"".join(chunks)

        def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            _close_pipe_handle(self._handle)

