from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from unittest.mock import patch

from vibemouse.config import ConfigStore, StatusStore, build_default_config_document
from vibemouse.core.backends.base import BackendStatus
from vibemouse.ipc.server import AgentCommandServer
from vibemouse.settings.server import SettingsServer


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
        return json.loads(response.read().decode("utf-8"))


def _request_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _request_raw(url: str) -> tuple[int, bytes]:
    with urlopen(url, timeout=5) as response:
        return response.status, response.read()


class _FakeStatusTranscriber:
    def availability(self, *, output_target: str = "default") -> BackendStatus:
        return BackendStatus(
            backend_id="sensevoice_fast",
            available=True,
            reason=None,
        )


class SettingsServerTests(unittest.TestCase):
    def test_favicon_request_returns_no_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            server = SettingsServer(config_path=config_path)
            server.start()
            try:
                status_code, body = _request_raw(f"{server.base_url}/favicon.ico")
            finally:
                server.stop()

        self.assertEqual(status_code, 204)
        self.assertEqual(body, b"")

    def test_root_serves_settings_page(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            server = SettingsServer(config_path=config_path)
            server.start()
            try:
                html = _request_text(f"{server.base_url}/")
            finally:
                server.stop()

        self.assertIn("<title>VibeMouse Settings</title>", html)
        self.assertIn('id="default-profile"', html)
        self.assertIn('id="translation-provider"', html)
        self.assertIn('id="translation-toast-enabled"', html)
        self.assertIn('id="readback-tts-enabled"', html)
        self.assertIn('id="readback-tts-voice"', html)
        self.assertIn('id="dictionary-table"', html)
        self.assertIn('id="backend-status"', html)

    def test_get_config_returns_profiles_and_dictionary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            document = build_default_config_document()
            document["profiles"]["default"] = "enhanced"
            document["dictionary"] = [
                {
                    "term": "Codex",
                    "phrases": ["codex", "code x"],
                    "weight": 8,
                    "scope": "both",
                    "enabled": True,
                }
            ]
            ConfigStore(config_path).save_document(document)

            server = SettingsServer(config_path=config_path)
            server.start()
            try:
                payload = _request_json("GET", f"{server.base_url}/api/config")
            finally:
                server.stop()

        self.assertEqual(payload["profiles"]["default"], "enhanced")
        self.assertEqual(payload["translation"]["provider"], "auto")
        self.assertEqual(payload["dictionary"][0]["term"], "Codex")
        self.assertEqual(payload["dictionary"][0]["phrases"], ["codex", "code x"])

    def test_post_config_persists_updates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            server = SettingsServer(config_path=config_path)
            server.start()
            try:
                document = build_default_config_document()
                document["profiles"]["default"] = "enhanced"
                document["output"]["translation_toast_enabled"] = False
                document["output"]["readback_tts_enabled"] = True
                document["output"]["readback_tts_voice"] = "en-US-EmmaMultilingualNeural"
                document["translation"]["provider"] = "deepl"
                document["translation"]["deepl_auth_key"] = "test-key"
                document["translation"]["deepl_api_url"] = "https://api-free.deepl.com/v2/translate"
                document["translation"]["libretranslate_url"] = "http://127.0.0.1:5000"
                document["dictionary"] = [
                    {
                        "term": "Claude Code",
                        "phrases": ["claude code", "cloud code"],
                        "weight": 7,
                        "scope": "default",
                        "enabled": True,
                    }
                ]
                payload = _request_json(
                    "POST",
                    f"{server.base_url}/api/config",
                    payload=document,
                )
            finally:
                server.stop()

            stored = ConfigStore(config_path).load_document()

        self.assertEqual(payload["profiles"]["default"], "enhanced")
        self.assertFalse(payload["output"]["translation_toast_enabled"])
        self.assertTrue(payload["output"]["readback_tts_enabled"])
        self.assertEqual(
            payload["output"]["readback_tts_voice"],
            "en-US-EmmaMultilingualNeural",
        )
        self.assertEqual(payload["translation"]["provider"], "deepl")
        self.assertEqual(payload["translation"]["deepl_auth_key"], "test-key")
        self.assertEqual(payload["dictionary"][0]["term"], "Claude Code")
        self.assertEqual(stored["profiles"]["default"], "enhanced")
        self.assertFalse(stored["output"]["translation_toast_enabled"])
        self.assertTrue(stored["output"]["readback_tts_enabled"])
        self.assertEqual(
            stored["output"]["readback_tts_voice"],
            "en-US-EmmaMultilingualNeural",
        )
        self.assertEqual(stored["translation"]["provider"], "deepl")
        self.assertEqual(stored["translation"]["libretranslate_url"], "http://127.0.0.1:5000")
        self.assertEqual(stored["dictionary"][0]["term"], "Claude Code")
        self.assertEqual(stored["dictionary"][0]["scope"], "default")

    def test_get_status_returns_backend_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            server = SettingsServer(
                config_path=config_path,
                transcriber_factory=lambda _config: _FakeStatusTranscriber(),
            )
            server.start()
            try:
                payload = _request_json("GET", f"{server.base_url}/api/status")
            finally:
                server.stop()

        self.assertEqual(payload["backends"]["default"]["backend_id"], "sensevoice_fast")
        self.assertTrue(payload["backends"]["default"]["available"])
        self.assertNotIn("openclaw", payload["backends"])

    def test_post_reload_reports_daemon_not_running_without_status_port(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            document = build_default_config_document()
            document["runtime"]["status_file"] = str(Path(tmp) / "status.json")
            ConfigStore(config_path).save_document(document)

            server = SettingsServer(config_path=config_path)
            with patch.dict(os.environ, {}, clear=True):
                server.start()
                try:
                    payload = _request_json("POST", f"{server.base_url}/api/reload")
                finally:
                    server.stop()

        self.assertEqual(
            payload,
            {"reloaded": False, "reason": "daemon_not_running"},
        )

    def test_post_reload_reports_invalid_config_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text("{broken", encoding="utf-8")

            server = SettingsServer(config_path=config_path)
            with patch.dict(os.environ, {}, clear=True):
                server.start()
                try:
                    payload = _request_json("POST", f"{server.base_url}/api/reload")
                finally:
                    server.stop()

        self.assertEqual(
            payload,
            {"reloaded": False, "reason": "config_unreadable:ValueError"},
        )

    def test_post_reload_sends_authenticated_reload_command(self) -> None:
        received: list[str] = []
        ready = threading.Event()

        def on_command(command_name: str) -> None:
            received.append(command_name)
            ready.set()

        with tempfile.TemporaryDirectory(prefix="vibemouse-settings-") as tmp:
            config_path = Path(tmp) / "config.json"
            status_path = Path(tmp) / "status.json"
            document = build_default_config_document()
            document["runtime"]["status_file"] = str(status_path)
            document["runtime"]["command_auth_token"] = "reload-secret"
            ConfigStore(config_path).save_document(document)

            command_server = AgentCommandServer(
                on_command=on_command,
                auth_token="reload-secret",
            )
            command_server.start()
            try:
                StatusStore(status_path).write(
                    {
                        "recording": False,
                        "state": "idle",
                        "ipc_port": command_server.port,
                    }
                )
                server = SettingsServer(config_path=config_path)
                with patch.dict(os.environ, {}, clear=True):
                    server.start()
                    try:
                        payload = _request_json("POST", f"{server.base_url}/api/reload")
                    finally:
                        server.stop()
                self.assertTrue(ready.wait(timeout=2))
            finally:
                command_server.stop()

        self.assertEqual(payload, {"reloaded": True, "reason": "reload_requested"})
        self.assertEqual(received, ["reload_config"])
