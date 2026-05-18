from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from typing import Protocol

from vibemouse.config import AppConfig, ConfigStore, StatusStore, load_config
from vibemouse.core.backend_status import collect_backend_statuses
from vibemouse.core.backends import BackendStatus
from vibemouse.core.transcriber import SenseVoiceTranscriber
from vibemouse.ipc.messages import make_command_message, write_lpjson_frame


class _BackendStatusReader(Protocol):
    def availability(self, *, output_target: str = "default") -> BackendStatus: ...


TranscriberFactory = Callable[[AppConfig], _BackendStatusReader]


class SettingsServer:
    def __init__(
        self,
        *,
        config_path: str | Path,
        host: str = "127.0.0.1",
        port: int = 0,
        transcriber_factory: TranscriberFactory | None = None,
    ) -> None:
        self._config_path = Path(config_path)
        self._host = host
        self._port = port
        self._store = ConfigStore(self._config_path)
        self._transcriber_factory = (
            transcriber_factory
            if transcriber_factory is not None
            else lambda config: SenseVoiceTranscriber(config)
        )
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("SettingsServer has not been started")
        return int(self._server.server_port)

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self.port}"

    def start(self) -> None:
        if self._server is not None:
            return

        server = _Server(
            (self._host, self._port),
            _build_handler(self),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def wait(self) -> None:
        if self._thread is None:
            return
        self._thread.join()

    def get_config_document(self) -> dict[str, object]:
        return self._store.load_document()

    def save_config_document(self, document: Mapping[str, object]) -> dict[str, object]:
        self._store.save_document(document)
        return self._store.load_document()

    def request_daemon_reload(self) -> dict[str, object]:
        try:
            config = load_config(self._config_path)
        except Exception as error:
            return {
                "reloaded": False,
                "reason": f"config_unreadable:{error.__class__.__name__}",
            }
        try:
            status = StatusStore(config.status_file).read_document()
        except ValueError as error:
            return {
                "reloaded": False,
                "reason": f"status_unreadable:{error.__class__.__name__}",
            }
        raw_port = status.get("ipc_port")
        if not isinstance(raw_port, int) or raw_port <= 0:
            return {
                "reloaded": False,
                "reason": "daemon_not_running",
            }

        try:
            with socket.create_connection(("127.0.0.1", raw_port), timeout=1.5) as conn:
                stream = conn.makefile("rwb")
                try:
                    write_lpjson_frame(
                        stream,
                        make_command_message(
                            "reload_config",
                            auth_token=config.command_auth_token,
                        ),
                    )
                finally:
                    stream.close()
        except OSError as error:
            return {
                "reloaded": False,
                "reason": f"reload_failed:{error.__class__.__name__}",
            }

        return {
            "reloaded": True,
            "reason": "reload_requested",
        }

    def get_backend_status_payload(self) -> dict[str, dict[str, object]]:
        config = load_config(self._config_path, env={})
        transcriber = self._transcriber_factory(config)
        statuses = collect_backend_statuses(transcriber)
        return {
            target: {
                "backend_id": status.backend_id,
                "available": status.available,
                "reason": status.reason,
            }
            for target, status in statuses.items()
        }


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _build_handler(settings_server: SettingsServer) -> type[BaseHTTPRequestHandler]:
    class SettingsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path in {"/", "/index.html", "/app.js", "/styles.css"}:
                self._send_static(self.path)
                return
            if self.path == "/api/config":
                self._send_json(HTTPStatus.OK, settings_server.get_config_document())
                return
            if self.path == "/api/status":
                self._send_json(
                    HTTPStatus.OK,
                    {"backends": settings_server.get_backend_status_payload()},
                )
                return
            if self.path == "/api/reload":
                self._send_json(HTTPStatus.OK, settings_server.request_daemon_reload())
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/reload":
                self._send_json(HTTPStatus.OK, settings_server.request_daemon_reload())
                return

            if self.path != "/api/config":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return

            try:
                payload = self._read_json_body()
                document = settings_server.save_config_document(payload)
            except ValueError as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return

            self._send_json(HTTPStatus.OK, document)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _send_static(self, request_path: str) -> None:
            asset_name = "index.html" if request_path in {"/", "/index.html"} else request_path.lstrip("/")
            asset_path = Path(__file__).with_name("static") / asset_name
            if not asset_path.exists():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return

            body = asset_path.read_bytes()
            content_type = guess_type(str(asset_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, object]:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as error:
                raise ValueError("Invalid Content-Length header") from error

            body = self.rfile.read(max(0, length))
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON payload: {error}") from error

            if not isinstance(payload, dict):
                raise ValueError("JSON payload must be an object")
            return {str(key): value for key, value in payload.items()}

        def _send_json(self, status: HTTPStatus, payload: Mapping[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SettingsHandler
