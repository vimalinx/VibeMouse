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
    run_deploy,
)


class DeployHelpersTests(unittest.TestCase):
    def test_build_deploy_env_applies_preset_and_override(self) -> None:
        env_map = build_deploy_env(
            preset="fast",
            command_auth_token="  reload-secret  ",
        )

        self.assertEqual(env_map["VIBEMOUSE_BACKEND"], "funasr_onnx")
        self.assertEqual(env_map["VIBEMOUSE_COMMAND_AUTH_TOKEN"], "reload-secret")
        self.assertEqual(env_map["VIBEMOUSE_BUTTON_DEBOUNCE_MS"], "120")

    def test_render_env_file_quotes_values(self) -> None:
        content = render_env_file(
            {
                "VIBEMOUSE_COMMAND_AUTH_TOKEN": "reload secret",
                "VIBEMOUSE_ENTER_MODE": "ctrl_enter",
            }
        )

        self.assertIn('VIBEMOUSE_COMMAND_AUTH_TOKEN="reload secret"', content)
        self.assertIn('VIBEMOUSE_ENTER_MODE="ctrl_enter"', content)

    def test_render_service_file_contains_paths(self) -> None:
        env_file = Path("/tmp/vibemouse.env")
        working_directory = Path("/work/vibemouse")
        log_file = Path("/tmp/vibemouse.log")
        service = render_service_file(
            env_file=env_file,
            working_directory=working_directory,
            log_file=log_file,
            exec_start="/tmp/vibemouse run",
        )

        self.assertIn("EnvironmentFile=/tmp/vibemouse.env", service)
        self.assertIn("WorkingDirectory=/work/vibemouse", service)
        self.assertIn("ExecStart=/tmp/vibemouse run", service)
        self.assertIn("ExecStartPre=/usr/bin/mkdir -p /tmp", service)
        self.assertIn("StandardOutput=append:/tmp/vibemouse.log", service)
        self.assertIn("StandardError=append:/tmp/vibemouse.log", service)


class DeployCommandTests(unittest.TestCase):
    def test_run_deploy_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-deploy-") as tmp:
            env_file = Path(tmp) / "deploy.env"
            service_file = Path(tmp) / "vibemouse.service"
            args = argparse.Namespace(
                preset="stable",
                env_file=str(env_file),
                service_file=str(service_file),
                working_directory=str(Path(tmp) / "repo"),
                log_file=str(Path(tmp) / "service.log"),
                command_auth_token=None,
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
                working_directory=str(Path(tmp) / "repo"),
                log_file=str(Path(tmp) / "service.log"),
                command_auth_token="reload-secret",
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
            self.assertIn('VIBEMOUSE_COMMAND_AUTH_TOKEN="reload-secret"', env_file.read_text())

    def test_run_deploy_rejects_unknown_preset(self) -> None:
        args = argparse.Namespace(
            preset="unknown",
            env_file="/tmp/deploy.env",
            service_file="/tmp/vibemouse.service",
            working_directory="/tmp/repo",
            log_file="/tmp/vibemouse.log",
            command_auth_token=None,
            exec_start="/tmp/vibemouse run",
            skip_systemctl=True,
            dry_run=True,
        )
        rc = run_deploy(args)
        self.assertEqual(rc, 1)
