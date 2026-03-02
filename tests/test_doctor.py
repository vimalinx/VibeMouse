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
    _apply_doctor_fixes,
    _check_transcriber_dependencies,
    _ensure_user_service_active,
    _fix_hyprland_return_bind_conflict,
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

            with (
                patch("vibemouse.doctor.Path.home", return_value=Path(tmp)),
                patch("vibemouse.doctor.sys.platform", "linux"),
                patch.dict(
                    "os.environ",
                    {"HYPRLAND_INSTANCE_SIGNATURE": "test"},
                    clear=True,
                ),
            ):
                check = _check_hyprland_return_bind_conflict(
                    cast(
                        AppConfig,
                        cast(object, SimpleNamespace(rear_button="x1")),
                    )
                )

        self.assertEqual(check.status, "fail")
        self.assertIn("conflicting return bind", check.detail)

    def test_hyprland_bind_conflict_skips_on_non_linux(self) -> None:
        with patch("vibemouse.doctor.sys.platform", "darwin"):
            check = _check_hyprland_return_bind_conflict(
                cast(AppConfig, cast(object, SimpleNamespace(rear_button="x1")))
            )

        self.assertEqual(check.status, "ok")
        self.assertIn("non-linux", check.detail)

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

    def test_fix_hyprland_return_bind_conflict_comments_conflicting_lines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-doctor-fix-") as tmp:
            bind_path = (
                Path(tmp) / ".config" / "hypr" / "UserConfigs" / "UserKeybinds.conf"
            )
            bind_path.parent.mkdir(parents=True, exist_ok=True)
            _ = bind_path.write_text(
                "bind = , mouse:275, sendshortcut, , Return, activewindow\n"
                "bind = , mouse:276, sendshortcut, , Return, activewindow\n",
                encoding="utf-8",
            )

            with (
                patch("vibemouse.doctor.Path.home", return_value=Path(tmp)),
                patch("vibemouse.doctor.sys.platform", "linux"),
                patch.dict(
                    "os.environ",
                    {"HYPRLAND_INSTANCE_SIGNATURE": "test"},
                    clear=True,
                ),
                patch("vibemouse.doctor._run_subprocess") as run_subprocess,
            ):
                _fix_hyprland_return_bind_conflict()

            content = bind_path.read_text(encoding="utf-8")
            self.assertIn("auto-disabled by vibemouse doctor --fix", content)
            self.assertEqual(run_subprocess.call_count, 1)

    def test_ensure_user_service_active_restarts_when_inactive(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, timeout: float) -> SimpleNamespace:
            _ = timeout
            calls.append(cmd)
            if cmd[-2:] == ["is-active", "vibemouse.service"]:
                return SimpleNamespace(returncode=3, stdout="inactive\n")
            return SimpleNamespace(returncode=0, stdout="")

        with (
            patch("vibemouse.doctor._run_subprocess", side_effect=fake_run),
            patch("vibemouse.doctor.sys.platform", "linux"),
        ):
            _ensure_user_service_active()

        self.assertEqual(
            calls,
            [
                ["systemctl", "--user", "is-active", "vibemouse.service"],
                ["systemctl", "--user", "restart", "vibemouse.service"],
            ],
        )

    def test_apply_doctor_fixes_runs_both_fixers(self) -> None:
        with (
            patch("vibemouse.doctor._fix_hyprland_return_bind_conflict") as fix_bind,
            patch("vibemouse.doctor._ensure_user_service_active") as fix_service,
        ):
            _apply_doctor_fixes()

        self.assertEqual(fix_bind.call_count, 1)
        self.assertEqual(fix_service.call_count, 1)


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
            patch("vibemouse.doctor._check_transcriber_dependencies") as transcriber_dep_check,
            patch("vibemouse.doctor._check_input_device_permissions") as input_check,
            patch("vibemouse.doctor._check_user_service_state") as service_check,
        ):
            bind_check.return_value = DoctorCheck("bind", "ok", "ok")
            audio_check.return_value = DoctorCheck("audio", "ok", "ok")
            transcriber_dep_check.return_value = DoctorCheck("deps", "ok", "ok")
            input_check.return_value = DoctorCheck("input", "ok", "ok")
            service_check.return_value = DoctorCheck("service", "ok", "ok")
            rc = run_doctor()

        self.assertEqual(rc, 1)

    def test_run_doctor_with_fix_invokes_fix_path(self) -> None:
        with (
            patch("vibemouse.doctor._apply_doctor_fixes") as apply_fixes,
            patch(
                "vibemouse.doctor._check_config_load",
                return_value=(
                    DoctorCheck("config", "ok", "ok"),
                    cast(
                        AppConfig,
                        cast(
                            object,
                            SimpleNamespace(
                                openclaw_command="openclaw",
                                openclaw_agent="main",
                                rear_button="x2",
                                sample_rate=16000,
                                channels=1,
                            ),
                        ),
                    ),
                ),
            ),
            patch("vibemouse.doctor._check_openclaw", return_value=[]),
            patch(
                "vibemouse.doctor._check_audio_input",
                return_value=DoctorCheck("audio", "ok", "ok"),
            ),
            patch(
                "vibemouse.doctor._check_transcriber_dependencies",
                return_value=DoctorCheck("deps", "ok", "ok"),
            ),
            patch(
                "vibemouse.doctor._check_input_device_permissions",
                return_value=DoctorCheck("input", "ok", "ok"),
            ),
            patch(
                "vibemouse.doctor._check_hyprland_return_bind_conflict",
                return_value=DoctorCheck("bind", "ok", "ok"),
            ),
            patch(
                "vibemouse.doctor._check_user_service_state",
                return_value=DoctorCheck("service", "ok", "ok"),
            ),
        ):
            rc = run_doctor(apply_fixes=True)

        self.assertEqual(rc, 0)
        self.assertEqual(apply_fixes.call_count, 1)

    def test_check_transcriber_dependencies_reports_missing_module(self) -> None:
        config = cast(
            AppConfig,
            cast(
                object,
                SimpleNamespace(transcriber_backend="funasr", device="cpu"),
            ),
        )
        with patch(
            "vibemouse.doctor.importlib.import_module",
            side_effect=ModuleNotFoundError("funasr"),
        ):
            check = _check_transcriber_dependencies(config)

        self.assertEqual(check.status, "fail")
        self.assertIn("cannot import funasr", check.detail)
