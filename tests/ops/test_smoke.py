from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from vibemouse.config import ConfigStore, build_default_config_document
from vibemouse.ops.smoke import run_smoke


class SmokeCommandTests(unittest.TestCase):
    def test_run_smoke_succeeds_with_isolated_default_config(self) -> None:
        rc, output = _run_smoke_capture(SimpleNamespace(config=None))

        self.assertEqual(rc, 0)
        self.assertIn("[OK] config-load:", output)
        self.assertIn("[OK] settings-reload-authenticated:", output)
        self.assertIn("[OK] command-auth:", output)
        self.assertIn("Smoke summary: 7 checks, 0 fail, 0 warn", output)

    def test_run_smoke_validates_config_without_touching_real_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-smoke-test-") as tmp:
            config_path = Path(tmp) / "config.json"
            real_status_path = Path(tmp) / "real-status.json"
            document = build_default_config_document()
            document["runtime"]["status_file"] = str(real_status_path)
            ConfigStore(config_path).save_document(document)
            original_config = config_path.read_text(encoding="utf-8")

            rc, output = _run_smoke_capture(SimpleNamespace(config=str(config_path)))

            self.assertEqual(rc, 0)
            self.assertIn(f"[OK] config-load: validated {config_path}", output)
            self.assertFalse(real_status_path.exists())
            self.assertEqual(config_path.read_text(encoding="utf-8"), original_config)

    def test_run_smoke_fails_for_invalid_config_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-smoke-test-") as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text("{broken", encoding="utf-8")

            rc, output = _run_smoke_capture(SimpleNamespace(config=str(config_path)))

        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] config-load:", output)
        self.assertIn("failed to prepare smoke config", output)
        self.assertIn("Smoke summary: 1 checks, 1 fail, 0 warn", output)

    def test_run_smoke_fails_for_missing_config_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-smoke-test-") as tmp:
            missing_path = Path(tmp) / "missing.json"

            rc, output = _run_smoke_capture(SimpleNamespace(config=str(missing_path)))

        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] config-load:", output)
        self.assertIn("config file not found", output)


def _run_smoke_capture(args: SimpleNamespace) -> tuple[int, str]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = run_smoke(args)
    return rc, stdout.getvalue()
