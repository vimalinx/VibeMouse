from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vibemouse.deploy import (
    _resolve_exec_start,
    build_deploy_env,
    render_env_file,
    render_service_file,
    run_deploy,
)


class DeployHelpersTests(unittest.TestCase):
    def test_resolve_exec_start_defaults_to_current_python_module_invocation(self) -> None:
        with patch("vibemouse.deploy.sys.executable", "/tmp/venv/bin/python"):
            exec_start = _resolve_exec_start("")

        self.assertEqual(exec_start, "/tmp/venv/bin/python -m vibemouse.main run")

    def test_build_deploy_env_applies_preset_and_override(self) -> None:
        env_map = build_deploy_env(
            preset="fast",
            openclaw_command="openclaw --profile prod",
            openclaw_agent="ops",
            openclaw_retries=5,
        )

        self.assertEqual(
            env_map["VIBEMOUSE_OPENCLAW_COMMAND"], "openclaw --profile prod"
        )
        self.assertEqual(env_map["VIBEMOUSE_OPENCLAW_AGENT"], "ops")
        self.assertEqual(env_map["VIBEMOUSE_OPENCLAW_RETRIES"], "5")
        self.assertEqual(env_map["VIBEMOUSE_BUTTON_DEBOUNCE_MS"], "120")

    def test_render_env_file_quotes_values(self) -> None:
        content = render_env_file(
            {
                "VIBEMOUSE_OPENCLAW_COMMAND": "openclaw --profile prod",
                "VIBEMOUSE_OPENCLAW_AGENT": "main",
            }
        )

        self.assertIn('VIBEMOUSE_OPENCLAW_COMMAND="openclaw --profile prod"', content)
        self.assertIn('VIBEMOUSE_OPENCLAW_AGENT="main"', content)

    def test_render_service_file_contains_paths(self) -> None:
        env_file = Path("/tmp/vibemouse.env")
        service = render_service_file(
            env_file=env_file, exec_start="/tmp/vibemouse run"
        )

        self.assertIn("EnvironmentFile=/tmp/vibemouse.env", service)
        self.assertIn("ExecStart=/tmp/vibemouse run", service)


class DeployCommandTests(unittest.TestCase):
    def test_run_deploy_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            service_file = Path(tmp) / "vibemouse.service"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                service_file=str(service_file),
                openclaw_command="openclaw",
                openclaw_agent="main",
                openclaw_retries=None,
                exec_start="/tmp/vibemouse run",
                skip_systemctl=True,
                dry_run=True,
            )

            rc = run_deploy(args)

        self.assertEqual(rc, 0)
        self.assertFalse(env_file.exists())
        self.assertFalse(service_file.exists())

    def test_run_deploy_skip_systemctl_writes_files_and_runs_doctor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            service_file = Path(tmp) / "vibemouse.service"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                service_file=str(service_file),
                openclaw_command="openclaw --profile prod",
                openclaw_agent="ops",
                openclaw_retries=2,
                exec_start="/tmp/vibemouse run",
                skip_systemctl=True,
                dry_run=False,
            )

            with patch("vibemouse.deploy.run_doctor", return_value=0) as run_doctor:
                rc = run_deploy(args)

            self.assertEqual(rc, 0)
            self.assertEqual(run_doctor.call_count, 1)
            self.assertTrue(env_file.exists())
            self.assertTrue(service_file.exists())
            self.assertIn('VIBEMOUSE_OPENCLAW_AGENT="ops"', env_file.read_text())

    def test_run_deploy_rejects_negative_retry_override(self) -> None:
        args = argparse.Namespace(
            preset="stable",
            env_file="/tmp/deploy.env",
            service_file="/tmp/vibemouse.service",
            openclaw_command="openclaw",
            openclaw_agent="main",
            openclaw_retries=-1,
            exec_start="/tmp/vibemouse run",
            skip_systemctl=True,
            dry_run=True,
        )
        rc = run_deploy(args)
        self.assertEqual(rc, 1)
