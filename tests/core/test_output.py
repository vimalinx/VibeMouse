from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

from vibemouse.output import TextOutput


class _FakeKeyboardController:
    def __init__(
        self,
        *,
        fail_on_press: bool = False,
        fail_on_press_key: object | None = None,
    ) -> None:
        self.events: list[tuple[str, object]] = []
        self._fail_on_press: bool = fail_on_press
        self._fail_on_press_key: object | None = fail_on_press_key

    def press(self, key: object) -> None:
        if self._fail_on_press or key == self._fail_on_press_key:
            raise RuntimeError("press failed")
        self.events.append(("press", key))

    def release(self, key: object) -> None:
        self.events.append(("release", key))

    def type(self, text: str) -> None:
        self.events.append(("type", text))


class TextOutputFocusProbeTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> TextOutput:
        return object.__new__(TextOutput)

    def test_focus_probe_uses_timeout_and_accepts_positive_result(self) -> None:
        captured_timeouts: list[float] = []

        def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
            _ = args
            timeout = kwargs.get("timeout")
            if isinstance(timeout, float):
                captured_timeouts.append(timeout)
            return SimpleNamespace(returncode=0, stdout="1\n")

        with (
            patch("vibemouse.system_integration.sys.platform", "linux"),
            patch("vibemouse.system_integration.subprocess.run", side_effect=fake_run),
        ):
            subject = self._make_subject()
            probe = cast(Callable[[], bool], getattr(subject, "_is_text_input_focused"))
            call_probe: Callable[[], bool] = probe
            result = call_probe()

        self.assertTrue(result)
        self.assertEqual(captured_timeouts, [1.5])

    def test_focus_probe_timeout_returns_false(self) -> None:
        with (
            patch("vibemouse.system_integration.sys.platform", "linux"),
            patch(
                "vibemouse.system_integration.subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["python3", "-c", "..."], timeout=1.5
                ),
            ),
        ):
            subject = self._make_subject()
            probe = cast(Callable[[], bool], getattr(subject, "_is_text_input_focused"))
            self.assertFalse(probe())

    def test_focus_probe_oserror_returns_false(self) -> None:
        with (
            patch("vibemouse.system_integration.sys.platform", "linux"),
            patch(
                "vibemouse.system_integration.subprocess.run",
                side_effect=OSError("spawn failed"),
            ),
        ):
            subject = self._make_subject()
            probe = cast(Callable[[], bool], getattr(subject, "_is_text_input_focused"))
            self.assertFalse(probe())

    def test_focus_probe_prefers_system_integration_result(self) -> None:
        subject = self._make_subject()
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(is_text_input_focused=lambda: True),
        )

        with patch(
            "vibemouse.output.probe_text_input_focus_via_atspi"
        ) as fallback_probe:
            probe = cast(Callable[[], bool], getattr(subject, "_is_text_input_focused"))
            self.assertTrue(probe())

        self.assertEqual(fallback_probe.call_count, 0)

    def test_focus_probe_falls_back_when_integration_returns_none(self) -> None:
        subject = self._make_subject()
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(is_text_input_focused=lambda: None),
        )

        with patch(
            "vibemouse.output.probe_text_input_focus_via_atspi",
            return_value=True,
        ) as fallback_probe:
            probe = cast(Callable[[], bool], getattr(subject, "_is_text_input_focused"))
            self.assertTrue(probe())

        self.assertEqual(fallback_probe.call_count, 1)


class TextOutputRoutingTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> TextOutput:
        return object.__new__(TextOutput)

    @staticmethod
    def _bind_keyboard(subject: TextOutput, keyboard: _FakeKeyboardController) -> None:
        setattr(subject, "_kb", keyboard)
        setattr(subject, "_ctrl_key", "CTRL")
        setattr(subject, "_shift_key", "SHIFT")
        setattr(subject, "_insert_key", "INSERT")
        setattr(subject, "_enter_key", "ENTER")
        setattr(subject, "_atspi", None)
        setattr(subject, "_hyprland_session", False)
        setattr(subject, "_openclaw_command", "openclaw")
        setattr(subject, "_openclaw_agent", None)
        setattr(subject, "_openclaw_timeout_s", 20.0)
        setattr(subject, "_openclaw_retries", 0)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(
                send_shortcut=lambda mod, key: False,
                is_terminal_window_active=lambda: None,
                paste_shortcuts=lambda terminal_active: (),
                send_enter_via_accessibility=lambda: None,
                is_text_input_focused=lambda: None,
            ),
        )

    def test_send_to_openclaw_success_returns_openclaw(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        with patch(
            "vibemouse.output.subprocess.Popen",
            return_value=SimpleNamespace(),
        ) as popen_mock:
            route = subject.send_to_openclaw("hello")
            detail = subject.send_to_openclaw_result("hello")

        self.assertEqual(route, "openclaw")
        self.assertEqual(
            popen_mock.call_args.args[0],
            ["openclaw", "agent", "--message", "hello", "--json"],
        )
        self.assertEqual(detail.route, "openclaw")
        self.assertEqual(detail.reason, "dispatched")

    def test_send_to_openclaw_includes_agent_when_configured(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_openclaw_agent", "ops")

        with patch(
            "vibemouse.output.subprocess.Popen",
            return_value=SimpleNamespace(),
        ) as popen_mock:
            route = subject.send_to_openclaw("hello")

        self.assertEqual(route, "openclaw")
        self.assertEqual(
            popen_mock.call_args.args[0],
            ["openclaw", "agent", "--message", "hello", "--json", "--agent", "ops"],
        )

    def test_send_to_openclaw_invalid_command_falls_back_to_clipboard(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_openclaw_command", 'openclaw "')

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
        ):
            route = subject.send_to_openclaw("hello")

        self.assertEqual(route, "clipboard")
        self.assertEqual(copy_mock.call_count, 1)

        detail = subject.send_to_openclaw_result("hello")
        self.assertEqual(detail.route, "clipboard")
        self.assertEqual(detail.reason, "invalid_command")

    def test_send_to_openclaw_spawn_error_falls_back_to_clipboard(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        with (
            patch(
                "vibemouse.output.subprocess.Popen",
                side_effect=OSError("openclaw missing"),
            ),
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
        ):
            route = subject.send_to_openclaw("hello")

        self.assertEqual(route, "clipboard")
        self.assertEqual(copy_mock.call_count, 1)

    def test_send_to_openclaw_retries_once_then_succeeds(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_openclaw_retries", 1)

        popen_side_effects = [
            OSError("temporary spawn failure"),
            SimpleNamespace(),
        ]
        with patch(
            "vibemouse.output.subprocess.Popen",
            side_effect=popen_side_effects,
        ) as popen_mock:
            detail = subject.send_to_openclaw_result("hello")

        self.assertEqual(detail.route, "openclaw")
        self.assertEqual(detail.reason, "dispatched_after_retry_1")
        self.assertEqual(popen_mock.call_count, 2)

    def test_send_to_openclaw_retries_exhausted_falls_back_to_clipboard(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_openclaw_retries", 1)

        with (
            patch(
                "vibemouse.output.subprocess.Popen",
                side_effect=OSError("spawn failure"),
            ),
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
        ):
            detail = subject.send_to_openclaw_result("hello")

        self.assertEqual(detail.route, "clipboard")
        self.assertEqual(detail.reason, "spawn_error:OSError")
        self.assertEqual(copy_mock.call_count, 1)

    @staticmethod
    def _not_focused() -> bool:
        return False

    def test_clipboard_route_without_auto_paste(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)

        copied: list[str] = []

        def fake_copy(text: str) -> None:
            copied.append(text)

        with patch("vibemouse.output.pyperclip.copy", side_effect=fake_copy):
            route = subject.inject_or_clipboard("  hello  ", auto_paste=False)

        self.assertEqual(route, "clipboard")
        self.assertEqual(copied, ["hello"])
        self.assertEqual(keyboard.events, [])

    def test_auto_paste_route_uses_ctrl_v(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)

        with patch("vibemouse.output.pyperclip.copy") as copy_mock:
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "v"),
                ("release", "v"),
                ("release", "CTRL"),
            ],
        )

    def test_auto_paste_uses_system_shortcut_candidates_when_available(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(
                send_shortcut=lambda mod, key: mod == "ALT" and key == "V",
                is_terminal_window_active=lambda: True,
                paste_shortcuts=lambda terminal_active: (("ALT", "V"),)
                if terminal_active
                else (),
                send_enter_via_accessibility=lambda: None,
                is_text_input_focused=lambda: None,
            ),
        )

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch("vibemouse.output.subprocess.run") as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 0)
        self.assertEqual(keyboard.events, [])

    def test_auto_paste_system_shortcuts_fall_back_to_keyboard(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(
                send_shortcut=lambda mod, key: False,
                is_terminal_window_active=lambda: True,
                paste_shortcuts=lambda terminal_active: (("ALT", "V"),)
                if terminal_active
                else (),
                send_enter_via_accessibility=lambda: None,
                is_text_input_focused=lambda: None,
            ),
        )

        with patch("vibemouse.output.pyperclip.copy") as copy_mock:
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "v"),
                ("release", "v"),
                ("release", "CTRL"),
            ],
        )

    def test_auto_paste_prefers_hyprland_sendshortcut(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", True)

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch.object(
                subject,
                "_is_hyprland_terminal_active",
                return_value=False,
            ),
            patch(
                "vibemouse.output.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
            ) as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(keyboard.events, [])

    def test_auto_paste_hyprland_failure_falls_back_to_ctrl_v(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", True)

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch.object(
                subject,
                "_is_hyprland_terminal_active",
                return_value=False,
            ),
            patch(
                "vibemouse.output.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stdout=""),
            ) as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "v"),
                ("release", "v"),
                ("release", "CTRL"),
            ],
        )

    def test_auto_paste_hyprland_terminal_prefers_ctrl_shift_v(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", True)

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch.object(
                subject,
                "_is_hyprland_terminal_active",
                return_value=True,
            ),
            patch(
                "vibemouse.output.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
            ) as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 1)
        run_args = cast(list[str], run_mock.call_args.args[0])
        self.assertEqual(
            run_args,
            ["hyprctl", "dispatch", "sendshortcut", "CTRL SHIFT, V, activewindow"],
        )
        self.assertEqual(keyboard.events, [])

    def test_auto_paste_hyprland_terminal_uses_shift_insert_fallback(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", True)

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch.object(
                subject,
                "_is_hyprland_terminal_active",
                return_value=True,
            ),
            patch(
                "vibemouse.output.subprocess.run",
                side_effect=[
                    SimpleNamespace(returncode=1, stdout=""),
                    SimpleNamespace(returncode=0, stdout="ok\n"),
                ],
            ) as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 2)
        first_args = cast(list[str], run_mock.call_args_list[0].args[0])
        second_args = cast(list[str], run_mock.call_args_list[1].args[0])
        self.assertEqual(
            first_args,
            ["hyprctl", "dispatch", "sendshortcut", "CTRL SHIFT, V, activewindow"],
        )
        self.assertEqual(
            second_args,
            ["hyprctl", "dispatch", "sendshortcut", "SHIFT, Insert, activewindow"],
        )
        self.assertEqual(keyboard.events, [])

    def test_auto_paste_hyprland_terminal_all_system_shortcuts_fail_falls_back_to_ctrl_shift_v_keyboard(
        self,
    ) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", True)

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch.object(
                subject,
                "_is_hyprland_terminal_active",
                return_value=True,
            ),
            patch(
                "vibemouse.output.subprocess.run",
                side_effect=[
                    SimpleNamespace(returncode=1, stdout=""),
                    SimpleNamespace(returncode=1, stdout=""),
                    SimpleNamespace(returncode=1, stdout=""),
                ],
            ) as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "SHIFT"),
                ("press", "v"),
                ("release", "v"),
                ("release", "SHIFT"),
                ("release", "CTRL"),
            ],
        )

    def test_auto_paste_hyprland_terminal_keyboard_shift_insert_fallback_when_ctrl_shift_v_fails(
        self,
    ) -> None:
        subject = self._make_subject()

        class _CtrlShiftVFailingKeyboard(_FakeKeyboardController):
            def press(self, key: object) -> None:
                if key == "v":
                    raise RuntimeError("v press failed")
                super().press(key)

        keyboard = _CtrlShiftVFailingKeyboard()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", True)

        with (
            patch("vibemouse.output.pyperclip.copy") as copy_mock,
            patch.object(
                subject,
                "_is_hyprland_terminal_active",
                return_value=True,
            ),
            patch(
                "vibemouse.output.subprocess.run",
                side_effect=[
                    SimpleNamespace(returncode=1, stdout=""),
                    SimpleNamespace(returncode=1, stdout=""),
                    SimpleNamespace(returncode=1, stdout=""),
                ],
            ) as run_mock,
        ):
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "SHIFT"),
                ("release", "SHIFT"),
                ("release", "CTRL"),
                ("press", "SHIFT"),
                ("press", "INSERT"),
                ("release", "INSERT"),
                ("release", "SHIFT"),
            ],
        )

    def test_auto_paste_non_hyprland_shortcut_failure_falls_back_to_ctrl_v(
        self,
    ) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", False)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(
                send_shortcut=lambda mod, key: False,
                is_terminal_window_active=lambda: True,
                paste_shortcuts=lambda terminal_active: (("ALT", "V"),)
                if terminal_active
                else (),
                send_enter_via_accessibility=lambda: None,
                is_text_input_focused=lambda: None,
            ),
        )

        with patch("vibemouse.output.pyperclip.copy") as copy_mock:
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "pasted")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "v"),
                ("release", "v"),
                ("release", "CTRL"),
            ],
        )

    def test_auto_paste_ctrl_v_failure_releases_ctrl_and_falls_back_to_clipboard(
        self,
    ) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController(fail_on_press_key="v")
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)
        setattr(subject, "_hyprland_session", False)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(
                send_shortcut=lambda mod, key: False,
                is_terminal_window_active=lambda: False,
                paste_shortcuts=lambda terminal_active: (),
                send_enter_via_accessibility=lambda: None,
                is_text_input_focused=lambda: None,
            ),
        )

        with patch("vibemouse.output.pyperclip.copy") as copy_mock:
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "clipboard")
        self.assertEqual(copy_mock.call_count, 1)
        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("release", "CTRL"),
            ],
        )

    def test_hyprland_terminal_detection_by_window_class(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_hyprland_session", True)

        with patch(
            "vibemouse.output.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout='{"class":"foot","initialClass":"foot","title":"OpenCode"}',
            ),
        ):
            probe = cast(
                Callable[[], bool],
                getattr(subject, "_is_hyprland_terminal_active"),
            )
            self.assertTrue(probe())

    def test_hyprland_terminal_detection_by_title_hint(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_hyprland_session", True)

        with patch(
            "vibemouse.output.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout='{"class":"Code","initialClass":"Code","title":"tmux"}',
            ),
        ):
            probe = cast(
                Callable[[], bool],
                getattr(subject, "_is_hyprland_terminal_active"),
            )
            self.assertTrue(probe())

    def test_hyprland_terminal_detection_false_for_non_terminal_window(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_hyprland_session", True)

        with patch(
            "vibemouse.output.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout='{"class":"chromium","initialClass":"chromium","title":"ChatGPT"}',
            ),
        ):
            probe = cast(
                Callable[[], bool],
                getattr(subject, "_is_hyprland_terminal_active"),
            )
            self.assertFalse(probe())

    def test_terminal_detection_prefers_system_integration(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(
                send_shortcut=lambda mod, key: False,
                is_terminal_window_active=lambda: True,
                paste_shortcuts=lambda terminal_active: (),
                send_enter_via_accessibility=lambda: None,
                is_text_input_focused=lambda: None,
            ),
        )

        with patch("vibemouse.output.subprocess.run") as run_mock:
            probe = cast(
                Callable[[], bool],
                getattr(subject, "_is_hyprland_terminal_active"),
            )
            self.assertTrue(probe())

        self.assertEqual(run_mock.call_count, 0)

    def test_auto_paste_failure_falls_back_to_clipboard(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_is_text_input_focused", self._not_focused)

        def fail_paste() -> None:
            raise RuntimeError("paste failure")

        setattr(subject, "_paste_clipboard", fail_paste)

        with patch("vibemouse.output.pyperclip.copy") as copy_mock:
            route = subject.inject_or_clipboard("hello", auto_paste=True)

        self.assertEqual(route, "clipboard")
        self.assertEqual(copy_mock.call_count, 1)

    def test_send_enter_uses_enter_mode(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        with patch("vibemouse.output.time.sleep"):
            subject.send_enter(mode="enter")

        self.assertEqual(keyboard.events, [("press", "ENTER"), ("release", "ENTER")])

    def test_send_enter_supports_none_mode(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        subject.send_enter(mode="none")

        self.assertEqual(keyboard.events, [])

    def test_send_enter_prefers_atspi_when_available(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

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

        setattr(subject, "_atspi", _FakeAtspi())

        subject.send_enter(mode="enter")

        self.assertEqual(keyboard.events, [])

    def test_send_enter_prefers_system_accessibility_when_available(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(send_enter_via_accessibility=lambda: True),
        )

        with patch("vibemouse.output.probe_send_enter_via_atspi") as probe_mock:
            subject.send_enter(mode="enter")

        self.assertEqual(probe_mock.call_count, 0)
        self.assertEqual(keyboard.events, [])

    def test_send_enter_falls_back_to_probe_when_integration_returns_none(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(
            subject,
            "_system_integration",
            SimpleNamespace(send_enter_via_accessibility=lambda: None),
        )

        with patch(
            "vibemouse.output.probe_send_enter_via_atspi", return_value=True
        ) as probe_mock:
            subject.send_enter(mode="enter")

        self.assertEqual(probe_mock.call_count, 1)
        self.assertEqual(keyboard.events, [])

    def test_send_enter_prefers_hyprland_sendshortcut_when_available(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)
        setattr(subject, "_hyprland_session", True)

        with patch(
            "vibemouse.output.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            subject.send_enter(mode="enter")

        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(keyboard.events, [])

    def test_send_enter_supports_ctrl_enter(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        with patch("vibemouse.output.time.sleep"):
            subject.send_enter(mode="ctrl_enter")

        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("press", "ENTER"),
                ("release", "ENTER"),
                ("release", "CTRL"),
            ],
        )

    def test_send_enter_ctrl_enter_failure_releases_modifier(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController(fail_on_press_key="ENTER")
        self._bind_keyboard(subject, keyboard)

        with self.assertRaisesRegex(RuntimeError, "press failed"):
            subject.send_enter(mode="ctrl_enter")

        self.assertEqual(
            keyboard.events,
            [
                ("press", "CTRL"),
                ("release", "CTRL"),
            ],
        )

    def test_send_enter_supports_shift_enter(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        with patch("vibemouse.output.time.sleep"):
            subject.send_enter(mode="shift_enter")

        self.assertEqual(
            keyboard.events,
            [
                ("press", "SHIFT"),
                ("press", "ENTER"),
                ("release", "ENTER"),
                ("release", "SHIFT"),
            ],
        )

    def test_send_enter_rejects_unknown_mode(self) -> None:
        subject = self._make_subject()
        keyboard = _FakeKeyboardController()
        self._bind_keyboard(subject, keyboard)

        with self.assertRaisesRegex(ValueError, "Unsupported enter mode"):
            subject.send_enter(mode="meta_enter")
