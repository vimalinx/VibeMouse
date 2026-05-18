from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from vibemouse.system_integration import (
    HyprlandSystemIntegration,
    NoopSystemIntegration,
    create_system_integration,
    detect_hyprland_session,
    is_browser_window_payload,
    is_fullscreen_window_payload,
    is_terminal_window_payload,
    probe_send_enter_via_atspi,
    probe_text_input_focus_via_atspi,
    show_system_notification,
)


class SystemIntegrationDetectionTests(unittest.TestCase):
    def test_detect_hyprland_by_desktop_name(self) -> None:
        env = {"XDG_CURRENT_DESKTOP": "Hyprland"}
        self.assertTrue(detect_hyprland_session(env=env))

    def test_detect_hyprland_by_instance_signature(self) -> None:
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "abc"}
        self.assertTrue(detect_hyprland_session(env=env))

    def test_detect_hyprland_false_when_no_markers(self) -> None:
        self.assertFalse(detect_hyprland_session(env={}))

    def test_factory_returns_hyprland_integration(self) -> None:
        integration = create_system_integration(env={"XDG_CURRENT_DESKTOP": "Hyprland"})
        self.assertIsInstance(integration, HyprlandSystemIntegration)

    def test_factory_returns_noop_integration(self) -> None:
        integration = create_system_integration(env={}, platform_name="linux")
        self.assertIsInstance(integration, NoopSystemIntegration)

    def test_factory_returns_noop_on_non_hyprland_windows(self) -> None:
        integration = create_system_integration(env={}, platform_name="win32")
        self.assertIsInstance(integration, NoopSystemIntegration)

    def test_factory_returns_noop_on_non_hyprland_macos(self) -> None:
        integration = create_system_integration(env={}, platform_name="darwin")
        self.assertIsInstance(integration, NoopSystemIntegration)


class HyprlandSystemIntegrationTests(unittest.TestCase):
    def test_send_shortcut_uses_hyprctl_dispatch(self) -> None:
        integration = HyprlandSystemIntegration()
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            ok = integration.send_shortcut(mod="CTRL SHIFT", key="V")

        self.assertTrue(ok)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["hyprctl", "dispatch", "sendshortcut", "CTRL SHIFT, V, activewindow"],
        )

    def test_switch_workspace_left_uses_expected_argument(self) -> None:
        integration = HyprlandSystemIntegration()
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            ok = integration.switch_workspace("left")

        self.assertTrue(ok)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["hyprctl", "dispatch", "workspace", "e-1"],
        )

    def test_switch_workspace_handles_timeout(self) -> None:
        integration = HyprlandSystemIntegration()
        with patch(
            "vibemouse.system_integration.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["hyprctl"], timeout=1.0),
        ):
            self.assertFalse(integration.switch_workspace("right"))

    def test_switch_workspace_is_skipped_when_active_window_is_fullscreen(self) -> None:
        integration = HyprlandSystemIntegration()
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout='{"class":"zen-browser","fullscreen":1}\n',
            ),
        ) as run_mock:
            ok = integration.switch_workspace("right")

        self.assertFalse(ok)
        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(run_mock.call_args.args[0], ["hyprctl", "-j", "activewindow"])

    def test_cursor_position_returns_tuple_from_json(self) -> None:
        integration = HyprlandSystemIntegration()
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout='{"x":120.5,"y":75}'),
        ):
            position = integration.cursor_position()

        self.assertEqual(position, (120, 75))

    def test_noop_focus_probe_returns_none(self) -> None:
        integration = NoopSystemIntegration()
        self.assertIsNone(integration.is_text_input_focused())

    def test_noop_enter_accessibility_returns_none(self) -> None:
        integration = NoopSystemIntegration()
        self.assertIsNone(integration.send_enter_via_accessibility())

    def test_hyprland_enter_accessibility_delegates_to_probe(self) -> None:
        integration = HyprlandSystemIntegration()
        with patch(
            "vibemouse.system_integration.probe_send_enter_via_atspi",
            return_value=True,
        ) as probe_mock:
            ok = integration.send_enter_via_accessibility()

        self.assertTrue(ok)
        self.assertEqual(probe_mock.call_count, 1)

    def test_hyprland_terminal_active_detection_uses_active_window_payload(
        self,
    ) -> None:
        integration = HyprlandSystemIntegration()
        with patch.object(
            integration,
            "active_window",
            return_value={"class": "foot", "initialClass": "foot", "title": "dev"},
        ):
            self.assertTrue(integration.is_terminal_window_active())

    def test_hyprland_paste_shortcuts_terminal_and_default(self) -> None:
        integration = HyprlandSystemIntegration()
        self.assertEqual(
            integration.paste_shortcuts(terminal_active=True),
            (("CTRL SHIFT", "V"), ("SHIFT", "Insert"), ("CTRL", "V")),
        )
        self.assertEqual(
            integration.paste_shortcuts(terminal_active=False),
            (("CTRL", "V"),),
        )

    def test_terminal_payload_detection_by_title_hint(self) -> None:
        payload = {"class": "Code", "initialClass": "Code", "title": "tmux"}
        self.assertTrue(is_terminal_window_payload(payload))

    def test_terminal_payload_detection_false_for_browser_window(self) -> None:
        payload = {
            "class": "chromium",
            "initialClass": "chromium",
            "title": "ChatGPT",
        }
        self.assertFalse(is_terminal_window_payload(payload))

    def test_browser_payload_detection_by_class_hint(self) -> None:
        payload = {
            "class": "zen-browser",
            "initialClass": "zen",
            "title": "ChatGPT",
        }
        self.assertTrue(is_browser_window_payload(payload))

    def test_browser_payload_detection_false_for_terminal_window(self) -> None:
        payload = {
            "class": "foot",
            "initialClass": "foot",
            "title": "shell",
        }
        self.assertFalse(is_browser_window_payload(payload))

    def test_fullscreen_payload_detection_supports_hyprland_fields(self) -> None:
        self.assertTrue(is_fullscreen_window_payload({"fullscreen": 1}))
        self.assertTrue(is_fullscreen_window_payload({"fullscreenClient": True}))
        self.assertTrue(is_fullscreen_window_payload({"fakeFullscreen": "true"}))
        self.assertFalse(is_fullscreen_window_payload({"fullscreen": 0}))

    def test_probe_text_input_focus_returns_true_when_script_outputs_one(self) -> None:
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="1\n"),
        ):
            self.assertTrue(probe_text_input_focus_via_atspi())

    def test_probe_text_input_focus_timeout_returns_false(self) -> None:
        with patch(
            "vibemouse.system_integration.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["python3"], timeout=1.5),
        ):
            self.assertFalse(probe_text_input_focus_via_atspi())

    def test_probe_send_enter_with_supplied_module_returns_true(self) -> None:
        class _FakeKeySynthType:
            PRESSRELEASE: object = object()

        class _FakeAtspi:
            KeySynthType: type[_FakeKeySynthType] = _FakeKeySynthType

            @staticmethod
            def generate_keyboard_event(
                keyval: int,
                keystring: str | None,
                synth_type: object,
            ) -> bool:
                _ = keyval
                _ = keystring
                _ = synth_type
                return True

        self.assertTrue(
            probe_send_enter_via_atspi(atspi_module=_FakeAtspi(), lazy_load=False)
        )

    def test_probe_send_enter_without_module_returns_false(self) -> None:
        self.assertFalse(probe_send_enter_via_atspi(atspi_module=None, lazy_load=False))

    def test_show_system_notification_uses_notify_send_on_linux(self) -> None:
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ) as run_mock:
            shown = show_system_notification(
                "English Translation",
                "Hello, world.",
                platform_name="linux",
            )

        self.assertTrue(shown)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["notify-send", "-t", "2000", "English Translation", "Hello, world."],
        )

    def test_show_system_notification_uses_osascript_on_macos(self) -> None:
        with patch(
            "vibemouse.system_integration.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ) as run_mock:
            shown = show_system_notification(
                "English Translation",
                "Hello, world.",
                platform_name="darwin",
            )

        self.assertTrue(shown)
        self.assertEqual(run_mock.call_args.args[0][:3], ["osascript", "-l", "JavaScript"])
