from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from vibemouse.config import ConfigStore, StatusStore, load_config


class ConfigStoreTests(unittest.TestCase):
    def test_missing_config_file_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-config-") as tmp:
            config_path = Path(tmp) / "config.json"

            config = load_config(config_path, env={})

        self.assertEqual(config.sample_rate, 16000)
        self.assertEqual(config.transcriber_backend, "funasr_onnx")
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.front_button, "x1")
        self.assertEqual(config.rear_button, "x2")
        expected_hotkeys = (16, 91, 134) if os.name == "nt" else (42, 125, 193)
        self.assertEqual(config.record_hotkey_keycodes, expected_hotkeys)
        self.assertEqual(config.status_file.name, "vibemouse-status.json")

    def test_json_config_values_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-config-") as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "bindings": {
                            "mouse.side_front.press": "send_enter",
                        },
                        "transcriber": {
                            "backend": "funasr",
                            "model_name": "custom/model",
                            "sample_rate": 22050,
                            "trust_remote_code": True,
                        },
                        "input": {
                            "gesture_trigger_button": "right",
                            "record_hotkey_keycodes": [30, 31, 32],
                        },
                        "output": {
                            "auto_paste": True,
                            "enter_mode": "ctrl_enter",
                        },
                        "logs": {
                            "level": "error",
                        },
                        "runtime": {
                            "status_file": str(Path(tmp) / "status.json"),
                            "temp_dir": str(Path(tmp) / "audio"),
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, env={})

        self.assertEqual(config.transcriber_backend, "funasr")
        self.assertEqual(config.model_name, "custom/model")
        self.assertEqual(config.sample_rate, 22050)
        self.assertTrue(config.trust_remote_code)
        self.assertEqual(config.gesture_trigger_button, "right")
        self.assertEqual(config.record_hotkey_keycodes, (30, 31, 32))
        self.assertEqual(
            config.bindings,
            {"mouse.side_front.press": "send_enter"},
        )
        self.assertTrue(config.auto_paste)
        self.assertEqual(config.enter_mode, "ctrl_enter")
        self.assertEqual(config.log_level, "ERROR")
        self.assertEqual(config.status_file.name, "status.json")
        self.assertEqual(config.temp_dir.name, "audio")

    def test_env_overrides_win_over_json_config(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-config-") as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "output": {"auto_paste": False},
                        "logs": {"level": "warning"},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                env={
                    "VIBEMOUSE_AUTO_PASTE": "true",
                    "VIBEMOUSE_LOG_LEVEL": "debug",
                },
            )

        self.assertTrue(config.auto_paste)
        self.assertEqual(config.log_level, "DEBUG")

    def test_legacy_flat_config_shape_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-config-") as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sample_rate": 8000,
                        "openclaw_command": "openclaw --profile ops",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, env={})

        self.assertEqual(config.sample_rate, 8000)
        self.assertEqual(config.openclaw_command, "openclaw --profile ops")

    def test_save_document_writes_normalized_config(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-config-") as tmp:
            config_path = Path(tmp) / "config.json"
            store = ConfigStore(config_path)

            store.save_document(
                {
                    "schema_version": 1,
                    "bindings": {
                        "mouse.side_front.press": "send_enter",
                    },
                    "input": {
                        "front_button": "x2",
                        "rear_button": "x1",
                        "record_hotkey_keycodes": [10, 20, 30],
                    },
                }
            )

            payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(
            payload["bindings"],
            {"mouse.side_front.press": "send_enter"},
        )
        self.assertEqual(payload["input"]["front_button"], "x2")
        self.assertEqual(payload["input"]["rear_button"], "x1")
        self.assertEqual(payload["input"]["record_hotkey_keycodes"], [10, 20, 30])
        self.assertIn("transcriber", payload)
        self.assertIn("runtime", payload)

    def test_invalid_binding_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-config-") as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "bindings": {
                            "mouse.side_front.press": "paste_now",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "bindings\\['mouse\\.side_front\\.press'\\] must be one of",
            ):
                _ = load_config(config_path, env={})


class StatusStoreTests(unittest.TestCase):
    def test_write_persists_normalized_status_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_path = Path(tmp) / "status.json"
            store = StatusStore(status_path)

            store.write(
                {
                    "recording": True,
                    "state": "recording",
                    "listener_mode": "inline",
                }
            )

            payload = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertEqual(
            payload,
            {
                "listener_mode": "inline",
                "recording": True,
                "state": "recording",
            },
        )

    def test_invalid_status_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_path = Path(tmp) / "status.json"
            store = StatusStore(status_path)

            with self.assertRaisesRegex(ValueError, "status.recording must be a boolean"):
                store.write({"recording": "yes", "state": "recording"})
