from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from vibemouse.config import AppConfig
from vibemouse.doctor import (
    DoctorCheck,
    _check_hyprland_return_bind_conflict,
    _check_openclaw,
    _parse_openclaw_command,
    run_doctor,
)


class DoctorHelpersTests(unittest.TestCase):
    def test_parse_openclaw_command_invalid_shell_syntax(self) -> None:
        self.assertIsNone(_parse_openclaw_command('openclaw "'))

    def test_check_openclaw_reports_missing_executable(self) -> None:
        config = cast(
            AppConfig,
            cast(
                object,
                SimpleNamespace(openclaw_command="openclaw", openclaw_agent="main"),
            ),
        )
        with patch("vibemouse.doctor.shutil.which", return_value=None):
            checks = _check_openclaw(config)

        self.assertEqual(checks[0].status, "fail")
        self.assertIn("executable not found", checks[0].detail)

    def test_check_openclaw_reports_agent_exists(self) -> None:
        config = cast(
            AppConfig,
            cast(
                object,
                SimpleNamespace(openclaw_command="openclaw", openclaw_agent="main"),
            ),
        )
        with (
            patch("vibemouse.doctor.shutil.which", return_value="/usr/bin/openclaw"),
            patch(
                "vibemouse.doctor.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0,
                    stdout='[{"id": "main"}]',
                    stderr="",
                ),
            ),
        ):
            checks = _check_openclaw(config)

        self.assertEqual([check.status for check in checks], ["ok", "ok"])

    def test_hyprland_bind_conflict_detection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-doctor-") as tmp:
            bind_path = (
                Path(tmp) / ".config" / "hypr" / "UserConfigs" / "UserKeybinds.conf"
            )
            bind_path.parent.mkdir(parents=True, exist_ok=True)
            _ = bind_path.write_text(
                "bind = , mouse:275, sendshortcut, , Return, activewindow\n",
                encoding="utf-8",
            )

            with patch("vibemouse.doctor.Path.home", return_value=Path(tmp)):
                check = _check_hyprland_return_bind_conflict(
                    cast(
                        AppConfig,
                        cast(object, SimpleNamespace(rear_button="x1")),
                    )
                )

        self.assertEqual(check.status, "fail")
        self.assertIn("conflicting return bind", check.detail)

    def test_audio_input_check_reports_missing_dependency(self) -> None:
        with patch(
            "vibemouse.doctor.importlib.import_module",
            side_effect=ModuleNotFoundError("sounddevice"),
        ):
            from vibemouse.doctor import _check_audio_input

            check = _check_audio_input(None)

        self.assertEqual(check.status, "fail")
        self.assertIn("cannot import sounddevice", check.detail)

    def test_audio_input_check_reports_ok_when_input_device_exists(self) -> None:
        fake_sounddevice = SimpleNamespace(
            query_devices=lambda: [{"max_input_channels": 2}],
            default=SimpleNamespace(device=(0, 1)),
            check_input_settings=lambda **kwargs: kwargs,
        )
        with patch(
            "vibemouse.doctor.importlib.import_module",
            return_value=fake_sounddevice,
        ):
            from vibemouse.doctor import _check_audio_input

            check = _check_audio_input(
                cast(
                    AppConfig,
                    cast(object, SimpleNamespace(sample_rate=16000, channels=1)),
                )
            )

        self.assertEqual(check.status, "ok")

    def test_input_permission_check_fails_when_all_devices_denied(self) -> None:
        fake_evdev = SimpleNamespace(
            list_devices=lambda: ["/dev/input/event0"],
            InputDevice=lambda path: (_ for _ in ()).throw(PermissionError(path)),
            ecodes=SimpleNamespace(EV_KEY=1, BTN_SIDE=0x116, BTN_EXTRA=0x117),
        )
        with (
            patch("vibemouse.doctor.sys.platform", "linux"),
            patch("vibemouse.doctor.importlib.import_module", return_value=fake_evdev),
        ):
            from vibemouse.doctor import _check_input_device_permissions

            check = _check_input_device_permissions(
                cast(AppConfig, cast(object, SimpleNamespace(rear_button="x1")))
            )

        self.assertEqual(check.status, "fail")
        self.assertIn("permission denied", check.detail)


class DoctorCommandTests(unittest.TestCase):
    def test_run_doctor_returns_nonzero_when_fail_exists(self) -> None:
        with (
            patch(
                "vibemouse.doctor._check_config_load",
                return_value=(
                    DoctorCheck("config", "fail", "broken"),
                    None,
                ),
            ),
            patch(
                "vibemouse.doctor._check_hyprland_return_bind_conflict"
            ) as bind_check,
            patch("vibemouse.doctor._check_audio_input") as audio_check,
            patch("vibemouse.doctor._check_input_device_permissions") as input_check,
            patch("vibemouse.doctor._check_user_service_state") as service_check,
        ):
            bind_check.return_value = DoctorCheck("bind", "ok", "ok")
            audio_check.return_value = DoctorCheck("audio", "ok", "ok")
            input_check.return_value = DoctorCheck("input", "ok", "ok")
            service_check.return_value = DoctorCheck("service", "ok", "ok")
            rc = run_doctor()

        self.assertEqual(rc, 1)
