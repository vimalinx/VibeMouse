from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from vibemouse.main import main


class MainEntryTests(unittest.TestCase):
    def test_doctor_subcommand_dispatches_to_doctor(self) -> None:
        with (
            patch("vibemouse.main.run_doctor", return_value=7) as run_doctor,
            patch("vibemouse.main.load_config") as load_config,
        ):
            rc = main(["doctor"])

        self.assertEqual(rc, 7)
        self.assertEqual(run_doctor.call_count, 1)
        self.assertEqual(run_doctor.call_args.kwargs, {"apply_fixes": False})
        self.assertEqual(load_config.call_count, 0)

    def test_doctor_fix_flag_is_forwarded(self) -> None:
        with patch("vibemouse.main.run_doctor", return_value=0) as run_doctor:
            rc = main(["doctor", "--fix"])

        self.assertEqual(rc, 0)
        self.assertEqual(run_doctor.call_count, 1)
        self.assertEqual(run_doctor.call_args.kwargs, {"apply_fixes": True})

    def test_default_invocation_runs_app(self) -> None:
        app_instance = MagicMock()
        cfg = SimpleNamespace(log_level="INFO")
        with (
            patch("vibemouse.main.load_config", return_value=cfg) as load_config,
            patch("vibemouse.main.resolve_config_path", return_value="/tmp/config.json"),
            patch(
                "vibemouse.main.VoiceMouseApp", return_value=app_instance
            ) as app_ctor,
        ):
            rc = main([])

        self.assertEqual(rc, 0)
        self.assertEqual(load_config.call_count, 1)
        self.assertEqual(app_ctor.call_count, 1)
        self.assertEqual(
            app_ctor.call_args.kwargs,
            {
                "listener_mode": "inline",
                "config_path": "/tmp/config.json",
            },
        )
        self.assertEqual(app_instance.run.call_count, 1)

    def test_explicit_run_subcommand_runs_app(self) -> None:
        app_instance = MagicMock()
        cfg = SimpleNamespace(log_level="INFO")
        with (
            patch("vibemouse.main.load_config", return_value=cfg),
            patch("vibemouse.main.resolve_config_path", return_value="/tmp/config.json"),
            patch("vibemouse.main.VoiceMouseApp", return_value=app_instance),
        ):
            rc = main(["run"])

        self.assertEqual(rc, 0)
        self.assertEqual(app_instance.run.call_count, 1)

    def test_agent_run_off_mode_is_forwarded_to_app(self) -> None:
        app_instance = MagicMock()
        cfg = SimpleNamespace(log_level="INFO")
        with (
            patch("vibemouse.main.load_config", return_value=cfg),
            patch(
                "vibemouse.main.resolve_config_path",
                return_value="/tmp/agent-config.json",
            ),
            patch("vibemouse.main.VoiceMouseApp", return_value=app_instance) as app_ctor,
        ):
            rc = main(["agent", "run", "--listener", "off"])

        self.assertEqual(rc, 0)
        self.assertEqual(
            app_ctor.call_args.kwargs,
            {
                "listener_mode": "off",
                "config_path": "/tmp/agent-config.json",
            },
        )
        self.assertEqual(app_instance.run.call_count, 1)

    def test_deploy_subcommand_dispatches_to_deploy(self) -> None:
        with (
            patch("vibemouse.main.run_deploy", return_value=5) as run_deploy,
            patch("vibemouse.main.load_config") as load_config,
        ):
            rc = main(["deploy", "--dry-run"])

        self.assertEqual(rc, 5)
        self.assertEqual(run_deploy.call_count, 1)
        self.assertEqual(load_config.call_count, 0)
