from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vibemouse.deploy import (
    build_deploy_env,
    render_env_file,
    render_service_file,
    render_windows_launcher,
    render_windows_startup_file,
    run_deploy,
)


class DeployHelpersTests(unittest.TestCase):
    def test_build_deploy_env_applies_preset_and_override(self) -> None:
        with patch("vibemouse.deploy._is_windows", return_value=False):
            env_map = build_deploy_env(
                preset="fast",
                openclaw_command="openclaw --profile prod",
                openclaw_agent="ops",
                openclaw_retries=5,
            )

        self.assertEqual(
            env_map["VIBEMOUSE_OPENCLAW_COMMAND"], "openclaw --profile prod"
        )
        self.assertEqual(env_map["VIBEMOUSE_BACKEND"], "funasr_onnx")
        self.assertEqual(env_map["VIBEMOUSE_OPENCLAW_AGENT"], "ops")
        self.assertEqual(env_map["VIBEMOUSE_OPENCLAW_RETRIES"], "5")
        self.assertEqual(env_map["VIBEMOUSE_BUTTON_DEBOUNCE_MS"], "120")

    def test_build_deploy_env_uses_windows_status_file_on_windows(self) -> None:
        with (
            patch("vibemouse.deploy._is_windows", return_value=True),
            patch(
                "vibemouse.deploy._windows_local_dir",
                return_value=Path("C:/Users/Test/AppData/Local"),
            ),
        ):
            env_map = build_deploy_env(
                preset="stable",
                openclaw_command="openclaw",
                openclaw_agent="main",
                openclaw_retries=None,
            )

        self.assertEqual(
            env_map["VIBEMOUSE_STATUS_FILE"],
            str(Path("C:/Users/Test/AppData/Local/VibeMouse/vibemouse-status.json")),
        )

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
        log_file = Path("/tmp/vibemouse.log")
        service = render_service_file(
            env_file=env_file,
            log_file=log_file,
            exec_start="/tmp/vibemouse run",
        )

        self.assertIn("EnvironmentFile=/tmp/vibemouse.env", service)
        self.assertIn("ExecStart=/tmp/vibemouse run", service)
        self.assertIn("ExecStartPre=/usr/bin/mkdir -p /tmp", service)
        self.assertIn("StandardOutput=append:/tmp/vibemouse.log", service)
        self.assertIn("StandardError=append:/tmp/vibemouse.log", service)

    def test_render_windows_launcher_contains_env_log_and_command(self) -> None:
        env_file = Path("C:/Temp/deploy.env")
        log_file = Path("C:/Temp/service.log")
        launcher = render_windows_launcher(
            env_file=env_file,
            log_file=log_file,
            exec_start='"C:/Python/python.exe" -m vibemouse.main run',
        )

        self.assertIn(str(env_file), launcher)
        self.assertIn(str(log_file), launcher)
        self.assertIn("-m vibemouse.main run", launcher)

    def test_render_windows_startup_file_points_to_launcher(self) -> None:
        startup = render_windows_startup_file(
            launcher_file=Path("C:/Temp/vibemouse-launch.ps1")
        )

        self.assertIn("powershell.exe", startup)
        self.assertIn("vibemouse-launch.ps1", startup)


class DeployCommandTests(unittest.TestCase):
    def test_run_deploy_linux_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            service_file = Path(tmp) / "vibemouse.service"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                service_file=str(service_file),
                log_file=str(Path(tmp) / "service.log"),
                openclaw_command="openclaw",
                openclaw_agent="main",
                openclaw_retries=None,
                exec_start="/tmp/vibemouse run",
                skip_systemctl=True,
                dry_run=True,
            )

            with patch("vibemouse.deploy._is_windows", return_value=False):
                rc = run_deploy(args)

        self.assertEqual(rc, 0)
        self.assertFalse(env_file.exists())
        self.assertFalse(service_file.exists())

    def test_run_deploy_windows_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            launcher_file = Path(tmp) / "vibemouse-launch.ps1"
            startup_file = Path(tmp) / "vibemouse.vbs"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                launcher_file=str(launcher_file),
                startup_file=str(startup_file),
                log_file=str(Path(tmp) / "service.log"),
                openclaw_command="openclaw",
                openclaw_agent="main",
                openclaw_retries=None,
                exec_start="python -m vibemouse.main run",
                skip_register=False,
                dry_run=True,
            )

            with patch("vibemouse.deploy._is_windows", return_value=True):
                rc = run_deploy(args)

        self.assertEqual(rc, 0)
        self.assertFalse(env_file.exists())
        self.assertFalse(launcher_file.exists())
        self.assertFalse(startup_file.exists())

    def test_run_deploy_linux_skip_systemctl_writes_files_and_runs_doctor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            service_file = Path(tmp) / "vibemouse.service"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                service_file=str(service_file),
                log_file=str(Path(tmp) / "service.log"),
                openclaw_command="openclaw --profile prod",
                openclaw_agent="ops",
                openclaw_retries=2,
                exec_start="/tmp/vibemouse run",
                skip_systemctl=True,
                dry_run=False,
            )

            with (
                patch("vibemouse.deploy._is_windows", return_value=False),
                patch("vibemouse.deploy.run_doctor", return_value=0) as run_doctor,
            ):
                rc = run_deploy(args)

            self.assertEqual(rc, 0)
            self.assertEqual(run_doctor.call_count, 1)
            self.assertTrue(env_file.exists())
            self.assertTrue(service_file.exists())
            self.assertIn('VIBEMOUSE_OPENCLAW_AGENT="ops"', env_file.read_text())

    def test_run_deploy_windows_writes_launcher_and_runs_doctor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            launcher_file = Path(tmp) / "vibemouse-launch.ps1"
            startup_file = Path(tmp) / "vibemouse.vbs"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                launcher_file=str(launcher_file),
                startup_file=str(startup_file),
                log_file=str(Path(tmp) / "service.log"),
                openclaw_command="openclaw --profile prod",
                openclaw_agent="ops",
                openclaw_retries=2,
                exec_start="python -m vibemouse.main run",
                skip_register=False,
                dry_run=False,
            )

            with (
                patch("vibemouse.deploy._is_windows", return_value=True),
                patch("vibemouse.deploy.run_doctor", return_value=0) as run_doctor,
            ):
                rc = run_deploy(args)

            self.assertEqual(rc, 0)
            self.assertEqual(run_doctor.call_count, 1)
            self.assertTrue(env_file.exists())
            self.assertTrue(launcher_file.exists())
            self.assertTrue(startup_file.exists())
            self.assertIn('VIBEMOUSE_OPENCLAW_AGENT="ops"', env_file.read_text())

    def test_run_deploy_rejects_negative_retry_override(self) -> None:
        args = argparse.Namespace(
            preset="stable",
            env_file="/tmp/deploy.env",
            service_file="/tmp/vibemouse.service",
            log_file="/tmp/vibemouse.log",
            openclaw_command="openclaw",
            openclaw_agent="main",
            openclaw_retries=-1,
            exec_start="/tmp/vibemouse run",
            skip_systemctl=True,
            dry_run=True,
        )
        with patch("vibemouse.deploy._is_windows", return_value=False):
            rc = run_deploy(args)
        self.assertEqual(rc, 1)
