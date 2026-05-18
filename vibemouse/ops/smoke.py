from __future__ import annotations

import copy
import json
import logging
import os
import socket
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen

from vibemouse.config import (
    ConfigStore,
    StatusStore,
    build_default_config_document,
    load_config,
)
from vibemouse.core.backends import BackendStatus
from vibemouse.ipc.messages import make_command_message, write_lpjson_frame
from vibemouse.ipc.server import AgentCommandServer
from vibemouse.settings import SettingsServer


_SMOKE_AUTH_TOKEN = "vibemouse-smoke-token"


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    detail: str


def run_smoke(args: SimpleNamespace | object | None = None) -> int:
    raw_config = getattr(args, "config", None) if args is not None else None
    config_path = Path(str(raw_config)).expanduser() if raw_config else None
    checks = run_smoke_checks(config_path=config_path)
    _print_checks(checks)
    fail_count = sum(1 for check in checks if check.status == "fail")
    warn_count = sum(1 for check in checks if check.status == "warn")
    print(f"Smoke summary: {len(checks)} checks, {fail_count} fail, {warn_count} warn")
    return 1 if fail_count else 0


def run_smoke_checks(*, config_path: Path | None = None) -> list[SmokeCheck]:
    with tempfile.TemporaryDirectory(prefix="vibemouse-smoke-") as tmp:
        work_dir = Path(tmp)
        try:
            smoke_config_path, smoke_status_path, source_detail = _prepare_smoke_config(
                config_path=config_path,
                work_dir=work_dir,
            )
        except Exception as error:
            return [
                SmokeCheck(
                    name="config-load",
                    status="fail",
                    detail=f"failed to prepare smoke config: {error}",
                )
            ]

        checks = [
            SmokeCheck(
                name="config-load",
                status="ok",
                detail=source_detail,
            )
        ]
        checks.append(_check_status_shapes(smoke_status_path))
        checks.extend(_check_settings_api(smoke_config_path, smoke_status_path))
        checks.append(_check_command_authentication())
        return checks


def _prepare_smoke_config(
    *,
    config_path: Path | None,
    work_dir: Path,
) -> tuple[Path, Path, str]:
    if config_path is None:
        document = build_default_config_document()
        source_detail = "loaded default config in isolated smoke workspace"
    else:
        if not config_path.exists():
            raise FileNotFoundError(f"config file not found: {config_path}")
        if not config_path.is_file():
            raise ValueError(f"config path is not a file: {config_path}")
        _ = load_config(config_path, env={})
        document = ConfigStore(config_path).load_document()
        source_detail = f"validated {config_path}"

    smoke_status_path = work_dir / "status.json"
    smoke_config_path = work_dir / "config.json"
    smoke_document = copy.deepcopy(document)
    runtime = smoke_document.setdefault("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    runtime["status_file"] = str(smoke_status_path)
    runtime["temp_dir"] = str(work_dir / "runtime")
    runtime["command_auth_token"] = _SMOKE_AUTH_TOKEN
    ConfigStore(smoke_config_path).save_document(smoke_document)
    _ = load_config(smoke_config_path, env={})
    return smoke_config_path, smoke_status_path, source_detail


def _check_status_shapes(status_path: Path) -> SmokeCheck:
    try:
        store = StatusStore(status_path)
        payloads = (
            {"recording": False, "state": "idle", "listener_mode": "off"},
            {"recording": True, "state": "recording", "listener_mode": "inline"},
            {
                "recording": False,
                "state": "processing",
                "listener_mode": "child",
                "last_transcript": "hello",
            },
        )
        for payload in payloads:
            store.write(payload)
            persisted = store.read_document()
            if persisted["state"] != payload["state"]:
                raise RuntimeError(f"state roundtrip mismatch: {payload['state']}")
    except Exception as error:
        return SmokeCheck(
            name="status-shapes",
            status="fail",
            detail=str(error),
        )
    return SmokeCheck(
        name="status-shapes",
        status="ok",
        detail="idle, recording, and processing payloads roundtrip",
    )


def _check_settings_api(
    config_path: Path,
    status_path: Path,
) -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    server = SettingsServer(
        config_path=config_path,
        transcriber_factory=lambda _config: _SmokeStatusTranscriber(),
    )
    with _without_vibemouse_env():
        server.start()
        try:
            checks.append(_check_settings_config_endpoint(server))
            checks.append(_check_settings_status_endpoint(server))
            checks.append(_check_reload_without_daemon(server))
            checks.append(_check_authenticated_reload(server, status_path))
        finally:
            server.stop()
    return checks


def _check_settings_config_endpoint(server: SettingsServer) -> SmokeCheck:
    try:
        payload = _request_json("GET", f"{server.base_url}/api/config")
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict) or profiles.get("default") not in {
            "fast",
            "enhanced",
        }:
            raise RuntimeError("config endpoint returned invalid profiles payload")
    except Exception as error:
        return SmokeCheck("settings-config", "fail", str(error))
    return SmokeCheck("settings-config", "ok", "GET /api/config returned profiles")


def _check_settings_status_endpoint(server: SettingsServer) -> SmokeCheck:
    try:
        payload = _request_json("GET", f"{server.base_url}/api/status")
        backends = payload.get("backends")
        if not isinstance(backends, dict):
            raise RuntimeError("status endpoint returned invalid backends payload")
        default_backend = backends.get("default")
        if not isinstance(default_backend, dict):
            raise RuntimeError("status endpoint omitted default backend")
        if default_backend.get("backend_id") != "smoke_backend":
            raise RuntimeError("status endpoint did not use smoke backend")
        if default_backend.get("available") is not True:
            raise RuntimeError("status endpoint did not report backend as available")
    except Exception as error:
        return SmokeCheck("settings-status", "fail", str(error))
    return SmokeCheck("settings-status", "ok", "GET /api/status returned backend state")


def _check_reload_without_daemon(server: SettingsServer) -> SmokeCheck:
    try:
        payload = _request_json("POST", f"{server.base_url}/api/reload")
        if payload != {"reloaded": False, "reason": "daemon_not_running"}:
            raise RuntimeError(f"unexpected reload response: {payload!r}")
    except Exception as error:
        return SmokeCheck("settings-reload-offline", "fail", str(error))
    return SmokeCheck(
        "settings-reload-offline",
        "ok",
        "POST /api/reload reports daemon_not_running without ipc_port",
    )


def _check_authenticated_reload(
    server: SettingsServer,
    status_path: Path,
) -> SmokeCheck:
    received: list[str] = []
    ready = threading.Event()

    def on_command(command_name: str) -> None:
        received.append(command_name)
        ready.set()

    command_server = AgentCommandServer(
        on_command=on_command,
        auth_token=_SMOKE_AUTH_TOKEN,
    )
    command_server.start()
    try:
        StatusStore(status_path).write(
            {
                "recording": False,
                "state": "idle",
                "listener_mode": "off",
                "ipc_port": command_server.port,
            }
        )
        payload = _request_json("POST", f"{server.base_url}/api/reload")
        if payload != {"reloaded": True, "reason": "reload_requested"}:
            raise RuntimeError(f"unexpected reload response: {payload!r}")
        if not ready.wait(timeout=2):
            raise RuntimeError("reload_config command was not received")
        if received != ["reload_config"]:
            raise RuntimeError(f"unexpected command sequence: {received!r}")
    except Exception as error:
        return SmokeCheck("settings-reload-authenticated", "fail", str(error))
    finally:
        command_server.stop()
    return SmokeCheck(
        "settings-reload-authenticated",
        "ok",
        "POST /api/reload delivered authenticated reload_config",
    )


def _check_command_authentication() -> SmokeCheck:
    received: list[str] = []
    ready = threading.Event()

    def on_command(command_name: str) -> None:
        received.append(command_name)
        ready.set()

    server = AgentCommandServer(on_command=on_command, auth_token=_SMOKE_AUTH_TOKEN)
    server.start()
    try:
        with _temporary_logger_level("vibemouse.ipc.server", logging.ERROR):
            _send_loopback_command(server.port, auth_token=None)
            if ready.wait(timeout=0.2):
                raise RuntimeError("unauthenticated command was accepted")
        _send_loopback_command(server.port, auth_token=_SMOKE_AUTH_TOKEN)
        if not ready.wait(timeout=2):
            raise RuntimeError("authenticated command was not accepted")
        if received != ["shutdown"]:
            raise RuntimeError(f"unexpected command sequence: {received!r}")
    except Exception as error:
        return SmokeCheck("command-auth", "fail", str(error))
    finally:
        server.stop()
    return SmokeCheck(
        "command-auth",
        "ok",
        "command server rejects missing token and accepts valid token",
    )


def _send_loopback_command(port: int, *, auth_token: str | None) -> None:
    with socket.create_connection(("127.0.0.1", port), timeout=2) as conn:
        stream = conn.makefile("rwb")
        try:
            write_lpjson_frame(
                stream,
                make_command_message("shutdown", auth_token=auth_token),
            )
        finally:
            stream.close()


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=5) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("JSON response must be an object")
    return {str(key): value for key, value in decoded.items()}


@contextmanager
def _without_vibemouse_env() -> Iterator[None]:
    saved = dict(os.environ)
    try:
        for key in tuple(os.environ):
            if key.startswith("VIBEMOUSE_"):
                del os.environ[key]
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@contextmanager
def _temporary_logger_level(logger_name: str, level: int) -> Iterator[None]:
    logger = logging.getLogger(logger_name)
    previous_level = logger.level
    logger.setLevel(level)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


def _print_checks(checks: list[SmokeCheck]) -> None:
    for check in checks:
        badge = {
            "ok": "OK",
            "warn": "WARN",
            "fail": "FAIL",
        }.get(check.status, check.status.upper())
        print(f"[{badge}] {check.name}: {check.detail}")


class _SmokeStatusTranscriber:
    def availability(self, *, output_target: str = "default") -> BackendStatus:
        _ = output_target
        return BackendStatus(
            backend_id="smoke_backend",
            available=True,
            reason=None,
        )
