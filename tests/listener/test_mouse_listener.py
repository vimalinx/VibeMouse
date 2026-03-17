from __future__ import annotations

import unittest
from collections.abc import Callable
from importlib import import_module as _real_import_module
from typing import cast
from unittest.mock import patch

from vibemouse.core.commands import EVENT_GESTURE_UP, EVENT_MOUSE_SIDE_FRONT_PRESS
from vibemouse.mouse_listener import SideButtonListener


def _noop_button() -> None:
    return


class _NeutralSystemIntegration:
    is_hyprland = True

    def active_window(self) -> dict[str, object] | None:
        return None

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        del mod, key
        return False

    def cursor_position(self) -> tuple[int, int] | None:
        return None

    def move_cursor(self, *, x: int, y: int) -> bool:
        del x, y
        return False

    def switch_workspace(self, direction: str) -> bool:
        del direction
        return False

    def is_text_input_focused(self) -> bool | None:
        return None

    def send_enter_via_accessibility(self) -> bool | None:
        return None

    def is_terminal_window_active(self) -> bool | None:
        return False

    def paste_shortcuts(
        self, *, terminal_active: bool
    ) -> tuple[tuple[str, str], ...]:
        del terminal_active
        return ()


class SideButtonListenerGestureTests(unittest.TestCase):
    @staticmethod
    def _classify(dx: int, dy: int, threshold_px: int) -> str | None:
        classify = cast(
            Callable[[int, int, int], str | None],
            getattr(SideButtonListener, "_classify_gesture"),
        )
        return classify(dx, dy, threshold_px)

    def test_classify_returns_none_when_movement_is_small(self) -> None:
        self.assertIsNone(self._classify(20, 10, 120))

    def test_classify_returns_right_for_positive_dx(self) -> None:
        self.assertEqual(self._classify(200, 30, 120), "right")

    def test_classify_returns_left_for_negative_dx(self) -> None:
        self.assertEqual(self._classify(-220, 10, 120), "left")

    def test_classify_returns_up_for_negative_dy(self) -> None:
        self.assertEqual(self._classify(20, -250, 120), "up")

    def test_classify_returns_down_for_positive_dy(self) -> None:
        self.assertEqual(self._classify(30, 240, 120), "down")

    def test_constructor_rejects_invalid_trigger_button(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "gesture_trigger_button must be one of: front, rear, right",
        ):
            _ = SideButtonListener(
                on_front_press=_noop_button,
                on_rear_press=_noop_button,
                front_button="x1",
                rear_button="x2",
                gesture_trigger_button="middle",
            )

    def test_constructor_accepts_right_trigger_button(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gesture_trigger_button="right",
        )

        self.assertIsNotNone(listener)

    def test_constructor_requires_event_or_button_callbacks(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "on_event or on_front_press/on_rear_press must be configured",
        ):
            _ = SideButtonListener(front_button="x1", rear_button="x2")

    def test_constructor_clamps_rescan_interval_to_minimum(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            rescan_interval_s=0.01,
        )

        rescan_interval = cast(float, getattr(listener, "_rescan_interval_s"))
        self.assertGreaterEqual(rescan_interval, 0.2)

    def test_dispatch_gesture_calls_callback_when_present(self) -> None:
        seen: list[str] = []

        def on_gesture(direction: str) -> None:
            seen.append(direction)

        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            on_gesture=on_gesture,
        )

        dispatch_gesture = cast(
            Callable[[str], None],
            getattr(listener, "_dispatch_gesture"),
        )
        dispatch_gesture("up")
        self.assertEqual(seen, ["up"])

    def test_dispatch_front_press_emits_normalized_event_when_configured(self) -> None:
        seen: list[str] = []
        listener = SideButtonListener(
            on_event=seen.append,
            front_button="x1",
            rear_button="x2",
            debounce_s=0.0,
        )

        dispatch_front = cast(
            Callable[[], None], getattr(listener, "_dispatch_front_press")
        )
        dispatch_front()

        self.assertEqual(seen, [EVENT_MOUSE_SIDE_FRONT_PRESS])

    def test_dispatch_gesture_emits_normalized_event_when_on_event_is_used(
        self,
    ) -> None:
        seen: list[str] = []
        listener = SideButtonListener(
            on_event=seen.append,
            front_button="x1",
            rear_button="x2",
        )

        dispatch_gesture = cast(
            Callable[[str], None],
            getattr(listener, "_dispatch_gesture"),
        )
        dispatch_gesture("up")

        self.assertEqual(seen, [EVENT_GESTURE_UP])

    def test_finish_gesture_restores_cursor_after_direction_action(self) -> None:
        seen: list[str] = []
        restored: list[tuple[int, int]] = []

        def on_gesture(direction: str) -> None:
            seen.append(direction)

        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            on_gesture=on_gesture,
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        with patch.object(listener, "_read_cursor_position", return_value=(100, 200)):
            start_capture = cast(
                Callable[..., None],
                getattr(listener, "_start_gesture_capture"),
            )
            start_capture(initial_position=(0, 0))

        accumulate = cast(
            Callable[..., None],
            getattr(listener, "_accumulate_gesture_delta"),
        )
        accumulate(dx=300, dy=0)

        def capture_restore(position: tuple[int, int]) -> None:
            restored.append(position)

        with patch.object(
            listener, "_restore_cursor_position", side_effect=capture_restore
        ):
            finish_capture = cast(
                Callable[[str], None],
                getattr(listener, "_finish_gesture_capture"),
            )
            finish_capture("right")

        self.assertEqual(seen, ["right"])
        self.assertEqual(restored, [(100, 200)])

    def test_finish_small_movement_does_not_restore_cursor(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        with patch.object(listener, "_read_cursor_position", return_value=(50, 60)):
            start_capture = cast(
                Callable[..., None],
                getattr(listener, "_start_gesture_capture"),
            )
            start_capture(initial_position=(0, 0))

        with patch.object(listener, "_restore_cursor_position") as restore_mock:
            finish_capture = cast(
                Callable[[str], None],
                getattr(listener, "_finish_gesture_capture"),
            )
            finish_capture("right")

        self.assertEqual(restore_mock.call_count, 0)

    def test_right_trigger_does_not_grab_source_device(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
            gesture_freeze_pointer=True,
        )

        fake_device = _GrabDeviceStub()
        start_capture = cast(
            Callable[..., None], getattr(listener, "_start_gesture_capture")
        )
        start_capture(source_device=fake_device, button_label="right")

        self.assertEqual(fake_device.grab_calls, 0)

    def test_non_right_trigger_can_grab_source_device(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="rear",
            gesture_freeze_pointer=True,
        )

        fake_device = _GrabDeviceStub()
        start_capture = cast(
            Callable[..., None], getattr(listener, "_start_gesture_capture")
        )
        start_capture(source_device=fake_device, button_label="rear")

        self.assertEqual(fake_device.grab_calls, 1)

    def test_right_trigger_does_not_capture_anchor_cursor(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
            gesture_restore_cursor=True,
        )

        with patch.object(listener, "_read_cursor_position", return_value=(11, 22)):
            start_capture = cast(
                Callable[..., None], getattr(listener, "_start_gesture_capture")
            )
            start_capture(initial_position=(0, 0), button_label="right")

        anchor = cast(
            tuple[int, int] | None, getattr(listener, "_gesture_anchor_cursor")
        )
        self.assertIsNone(anchor)

    def test_non_right_trigger_captures_anchor_cursor_when_enabled(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="rear",
            gesture_restore_cursor=True,
        )

        with patch.object(listener, "_read_cursor_position", return_value=(33, 44)):
            start_capture = cast(
                Callable[..., None], getattr(listener, "_start_gesture_capture")
            )
            start_capture(initial_position=(0, 0), button_label="rear")

        anchor = cast(
            tuple[int, int] | None, getattr(listener, "_gesture_anchor_cursor")
        )
        self.assertEqual(anchor, (33, 44))

    def test_button_suppress_grab_lifecycle(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
        )

        fake_device = _GrabDeviceStub()
        begin = cast(Callable[..., None], getattr(listener, "_begin_button_suppress"))
        end = cast(Callable[..., None], getattr(listener, "_end_button_suppress"))

        begin(source_device=fake_device, button_label="front")
        self.assertEqual(fake_device.grab_calls, 1)
        self.assertEqual(fake_device.ungrab_calls, 0)

        end(button_label="front")
        self.assertEqual(fake_device.ungrab_calls, 1)

    def test_button_suppress_ignores_mismatched_release_label(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
        )

        fake_device = _GrabDeviceStub()
        begin = cast(Callable[..., None], getattr(listener, "_begin_button_suppress"))
        end = cast(Callable[..., None], getattr(listener, "_end_button_suppress"))

        begin(source_device=fake_device, button_label="rear")
        end(button_label="front")
        self.assertEqual(fake_device.ungrab_calls, 0)

    def test_stale_button_grab_is_auto_released(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
        )

        fake_device = _GrabDeviceStub()
        begin = cast(Callable[..., None], getattr(listener, "_begin_button_suppress"))
        release_stale = cast(
            Callable[[], None], getattr(listener, "_release_stale_button_grab")
        )

        begin(source_device=fake_device, button_label="rear")
        setattr(listener, "_button_grab_deadline_monotonic", 0.0)
        release_stale()
        self.assertEqual(fake_device.ungrab_calls, 1)

    def test_release_button_grab_retries_after_ungrab_failure(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
        )

        fake_device = _GrabDeviceStub(fail_ungrab_times=1)
        begin = cast(Callable[..., None], getattr(listener, "_begin_button_suppress"))
        release = cast(Callable[[], None], getattr(listener, "_release_button_grab"))

        begin(source_device=fake_device, button_label="front")
        release()
        self.assertIs(getattr(listener, "_button_grabbed_device"), fake_device)

        release()
        self.assertEqual(fake_device.ungrab_calls, 2)
        self.assertIsNone(getattr(listener, "_button_grabbed_device"))

    def test_release_gesture_grab_retries_after_ungrab_failure(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="rear",
            gesture_freeze_pointer=True,
        )

        fake_device = _GrabDeviceStub(fail_ungrab_times=1)
        start_capture = cast(
            Callable[..., None], getattr(listener, "_start_gesture_capture")
        )
        release = cast(Callable[[], None], getattr(listener, "_release_gesture_grab"))

        start_capture(source_device=fake_device, button_label="rear")
        release()
        self.assertIs(getattr(listener, "_gesture_grabbed_device"), fake_device)

        release()
        self.assertEqual(fake_device.ungrab_calls, 2)
        self.assertIsNone(getattr(listener, "_gesture_grabbed_device"))

    def test_finish_small_movement_dispatches_click_async(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="rear",
        )

        start_capture = cast(
            Callable[..., None], getattr(listener, "_start_gesture_capture")
        )
        start_capture(initial_position=(0, 0), button_label="rear")

        with patch.object(listener, "_dispatch_click_async") as dispatch_click_async:
            finish_capture = cast(
                Callable[[str], None], getattr(listener, "_finish_gesture_capture")
            )
            finish_capture("rear")

        dispatch_click_async.assert_called_once_with("rear")

    def test_consume_right_trigger_release_skips_replay_after_small_drag(
        self,
    ) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        setattr(listener, "_right_trigger_pressed", True)
        setattr(listener, "_right_trigger_pressed_since", 100.0)
        setattr(listener, "_right_trigger_pending_dx", 20)
        setattr(listener, "_right_trigger_pending_dy", 10)
        setattr(listener, "_button_grabbed_label", "right")

        consume = cast(
            Callable[[], tuple[bool, str | None]],
            getattr(listener, "_consume_right_trigger_release"),
        )
        with (
            patch("vibemouse.mouse_listener.time.monotonic", return_value=100.1),
            patch.object(listener, "_end_button_suppress") as end_suppress,
        ):
            should_replay, gesture_direction = consume()

        self.assertFalse(should_replay)
        self.assertIsNone(gesture_direction)
        end_suppress.assert_called_once_with(button_label="right")
        self.assertFalse(cast(bool, getattr(listener, "_right_trigger_pressed")))


    def test_begin_right_trigger_press_passthroughs_native_wayland_browser(
        self,
    ) -> None:
        class _BrowserSystemIntegration:
            is_hyprland = True

            def active_window(self) -> dict[str, object] | None:
                return {
                    "class": "zen-browser",
                    "initialClass": "zen",
                    "title": "ChatGPT",
                    "xwayland": False,
                }

            def send_shortcut(self, *, mod: str, key: str) -> bool:
                del mod, key
                return False

            def cursor_position(self) -> tuple[int, int] | None:
                return None

            def move_cursor(self, *, x: int, y: int) -> bool:
                del x, y
                return False

            def switch_workspace(self, direction: str) -> bool:
                del direction
                return False

            def is_text_input_focused(self) -> bool | None:
                return None

            def send_enter_via_accessibility(self) -> bool | None:
                return None

            def is_terminal_window_active(self) -> bool | None:
                return False

            def paste_shortcuts(
                self, *, terminal_active: bool
            ) -> tuple[tuple[str, str], ...]:
                del terminal_active
                return ()

        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
            system_integration=_BrowserSystemIntegration(),
        )

        begin = cast(Callable[..., None], getattr(listener, "_begin_right_trigger_press"))

        with patch.object(listener, "_begin_button_suppress") as begin_suppress:
            begin(initial_position=(1, 2))

        self.assertTrue(cast(bool, getattr(listener, "_right_trigger_passthrough")))
        self.assertTrue(cast(bool, getattr(listener, "_right_trigger_pressed")))
        begin_suppress.assert_not_called()

    def test_passthrough_right_gesture_dispatches_on_large_move(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        setattr(listener, "_right_trigger_pressed", True)
        setattr(listener, "_right_trigger_passthrough", True)
        setattr(listener, "_right_trigger_pending_dx", 120)

        maybe_dispatch = cast(
            Callable[[], bool],
            getattr(listener, "_maybe_dispatch_passthrough_right_gesture"),
        )
        with patch.object(listener, "_dispatch_gesture") as dispatch_gesture:
            self.assertTrue(maybe_dispatch())

        dispatch_gesture.assert_called_once_with("right")
        self.assertFalse(cast(bool, getattr(listener, "_right_trigger_pressed")))
        self.assertFalse(cast(bool, getattr(listener, "_right_trigger_passthrough")))

    def test_consume_right_trigger_release_passthrough_returns_no_replay(
        self,
    ) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        setattr(listener, "_right_trigger_passthrough", True)
        consume = cast(
            Callable[[], tuple[bool, str | None]],
            getattr(listener, "_consume_right_trigger_release"),
        )

        should_replay, gesture_direction = consume()

        self.assertFalse(should_replay)
        self.assertIsNone(gesture_direction)
        self.assertFalse(cast(bool, getattr(listener, "_right_trigger_passthrough")))


    def test_stale_gesture_capture_force_releases_grab(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="rear",
            gesture_freeze_pointer=True,
        )

        fake_device = _GrabDeviceStub()
        start_capture = cast(
            Callable[..., None], getattr(listener, "_start_gesture_capture")
        )
        release_stale = cast(
            Callable[[], None], getattr(listener, "_release_stale_gesture_capture")
        )

        start_capture(source_device=fake_device, button_label="rear")
        self.assertEqual(fake_device.grab_calls, 1)

        setattr(listener, "_gesture_grab_timeout_s", 0.0)
        release_stale()

        self.assertEqual(fake_device.ungrab_calls, 1)
        self.assertFalse(cast(bool, getattr(listener, "_gesture_active")))

    def test_stale_right_hold_keeps_button_suppress_grab_before_timeout(
        self,
    ) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        fake_device = _GrabDeviceStub()
        begin = cast(Callable[..., None], getattr(listener, "_begin_button_suppress"))
        release_stale = cast(
            Callable[[], None], getattr(listener, "_release_stale_button_grab")
        )

        setattr(listener, "_right_trigger_pressed", True)
        setattr(listener, "_right_trigger_pressed_since", 100.0)
        with patch("vibemouse.mouse_listener.time.monotonic", return_value=100.0):
            begin(source_device=fake_device, button_label="right")
        with patch("vibemouse.mouse_listener.time.monotonic", return_value=105.0):
            release_stale()

        self.assertEqual(fake_device.ungrab_calls, 0)
        self.assertIs(getattr(listener, "_button_grabbed_device"), fake_device)

    def test_stale_right_hold_releases_button_suppress_grab_after_timeout(
        self,
    ) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        fake_device = _GrabDeviceStub()
        begin = cast(Callable[..., None], getattr(listener, "_begin_button_suppress"))
        release_stale = cast(
            Callable[[], None], getattr(listener, "_release_stale_button_grab")
        )

        setattr(listener, "_right_trigger_pressed", True)
        setattr(listener, "_right_trigger_pressed_since", 100.0)
        with patch("vibemouse.mouse_listener.time.monotonic", return_value=100.0):
            begin(source_device=fake_device, button_label="right")
        with patch("vibemouse.mouse_listener.time.monotonic", return_value=108.1):
            release_stale()

        self.assertEqual(fake_device.ungrab_calls, 1)
        self.assertIsNone(getattr(listener, "_button_grabbed_device"))
        self.assertFalse(cast(bool, getattr(listener, "_right_trigger_pressed")))


    def test_back_forward_aliases_match_x1_x2(self) -> None:
        class _FakeEvent:
            def __init__(self, event_type: int, code: int, value: int) -> None:
                self.type = event_type
                self.code = code
                self.value = value

        class _FakeDevice:
            def __init__(self, events: list[_FakeEvent], key_cap: list[int]) -> None:
                self.fd = 77
                self._events = events
                self._key_cap = key_cap

            def capabilities(self) -> dict[int, list[int]]:
                return {1: self._key_cap}

            def read(self) -> list[_FakeEvent]:
                events = self._events
                self._events = []
                return events

            def close(self) -> None:
                return

        events = [_FakeEvent(1, 278, 1), _FakeEvent(1, 277, 1)]
        fake_device = _FakeDevice(events=events, key_cap=[272, 277, 278])
        callbacks: list[str] = []

        def _on_front() -> None:
            callbacks.append("front")

        def _on_rear() -> None:
            callbacks.append("rear")
            listener._stop.set()

        listener = SideButtonListener(
            on_front_press=_on_front,
            on_rear_press=_on_rear,
            front_button="x1",
            rear_button="x2",
        )

        fake_ecodes = type(
            "_Ecodes",
            (),
            {
                "BTN_SIDE": 275,
                "BTN_EXTRA": 276,
                "BTN_BACK": 278,
                "BTN_FORWARD": 277,
                "BTN_LEFT": 272,
                "BTN_RIGHT": 273,
                "EV_KEY": 1,
                "EV_REL": 2,
                "REL_X": 0,
                "REL_Y": 1,
            },
        )
        fake_module = type(
            "_EvdevModule",
            (),
            {
                "InputDevice": lambda _path: fake_device,
                "ecodes": fake_ecodes,
                "list_devices": lambda: ["/dev/input/event-test"],
            },
        )

        def _import_module(name: str):
            if name == "evdev":
                return fake_module
            return _real_import_module(name)

        with (
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                side_effect=_import_module,
            ),
            patch("select.select", return_value=([77], [], [])),
        ):
            run_evdev = cast(Callable[[], None], getattr(listener, "_run_evdev"))
            run_evdev()

        self.assertEqual(callbacks, ["front", "rear"])

    def test_evdev_read_oserror_returns_for_hotplug(self) -> None:
        class _HotplugErrorDevice:
            def __init__(self) -> None:
                self.fd = 55

            def capabilities(self) -> dict[int, list[int]]:
                return {1: [272, 273, 275, 276]}

            def read(self) -> list[object]:
                raise OSError("No such device")

            def close(self) -> None:
                return

        fake_device = _HotplugErrorDevice()

        fake_ecodes = type(
            "_Ecodes",
            (),
            {
                "BTN_SIDE": 275,
                "BTN_EXTRA": 276,
                "BTN_BACK": 278,
                "BTN_FORWARD": 277,
                "BTN_LEFT": 272,
                "BTN_RIGHT": 273,
                "EV_KEY": 1,
                "EV_REL": 2,
                "REL_X": 0,
                "REL_Y": 1,
            },
        )
        fake_module = type(
            "_EvdevModule",
            (),
            {
                "InputDevice": lambda _path: fake_device,
                "ecodes": fake_ecodes,
                "list_devices": lambda: ["/dev/input/event-hotplug"],
            },
        )

        listener = SideButtonListener(
            on_front_press=lambda: None,
            on_rear_press=lambda: None,
            front_button="x1",
            rear_button="x2",
        )

        def _import_module(name: str):
            if name == "evdev":
                return fake_module
            return _real_import_module(name)

        with (
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                side_effect=_import_module,
            ),
            patch("select.select", return_value=([55], [], [])),
        ):
            run_evdev = cast(Callable[[], None], getattr(listener, "_run_evdev"))
            run_evdev()

    def test_right_trigger_tap_replays_right_click_after_release(self) -> None:
        class _FakeEvent:
            def __init__(self, event_type: int, code: int, value: int) -> None:
                self.type = event_type
                self.code = code
                self.value = value

        class _FakeDevice:
            def __init__(self, events: list[_FakeEvent], key_cap: list[int]) -> None:
                self.fd = 88
                self._events = events
                self._key_cap = key_cap

            def capabilities(self) -> dict[int, list[int]]:
                return {1: self._key_cap}

            def read(self) -> list[_FakeEvent]:
                events = self._events
                self._events = []
                return events

            def close(self) -> None:
                return

        right_code = 273
        events = [_FakeEvent(1, right_code, 1), _FakeEvent(1, right_code, 0)]
        fake_device = _FakeDevice(events=events, key_cap=[272, 273, 275, 276])

        fake_ecodes = type(
            "_Ecodes",
            (),
            {
                "BTN_SIDE": 275,
                "BTN_EXTRA": 276,
                "BTN_BACK": 278,
                "BTN_FORWARD": 277,
                "BTN_LEFT": 272,
                "BTN_RIGHT": right_code,
                "EV_KEY": 1,
                "EV_REL": 2,
                "REL_X": 0,
                "REL_Y": 1,
            },
        )
        fake_module = type(
            "_EvdevModule",
            (),
            {
                "InputDevice": lambda _path: fake_device,
                "ecodes": fake_ecodes,
                "list_devices": lambda: ["/dev/input/event-right"],
            },
        )

        listener = SideButtonListener(
            on_front_press=lambda: None,
            on_rear_press=lambda: None,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
            system_integration=_NeutralSystemIntegration(),
        )

        def _import_module(name: str):
            if name == "evdev":
                return fake_module
            return _real_import_module(name)

        def _mark_begin(*, source_device: object, button_label: str) -> None:
            self.assertIs(source_device, fake_device)
            self.assertEqual(button_label, "right")
            setattr(listener, "_button_grabbed_label", "right")

        def _dispatch_and_stop(button_label: str) -> None:
            self.assertEqual(button_label, "right")
            listener._stop.set()

        with (
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                side_effect=_import_module,
            ),
            patch("select.select", return_value=([88], [], [])),
            patch.object(
                listener,
                "_begin_button_suppress",
                side_effect=_mark_begin,
            ) as begin_suppress,
            patch.object(listener, "_end_button_suppress") as end_suppress,
            patch.object(listener, "_dispatch_gesture") as dispatch_gesture,
            patch.object(
                listener,
                "_dispatch_click_async",
                side_effect=_dispatch_and_stop,
            ) as dispatch_click_async,
        ):
            run_evdev = cast(Callable[[], None], getattr(listener, "_run_evdev"))
            run_evdev()

        self.assertEqual(begin_suppress.call_count, 1)
        end_suppress.assert_called_once_with(button_label="right")
        dispatch_gesture.assert_not_called()
        dispatch_click_async.assert_called_once_with("right")


    def test_consume_right_trigger_release_skips_replay_after_hold(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        setattr(listener, "_right_trigger_pressed", True)
        setattr(listener, "_right_trigger_pressed_since", 100.0)
        setattr(listener, "_button_grabbed_label", "right")

        consume = cast(
            Callable[[], tuple[bool, str | None]],
            getattr(listener, "_consume_right_trigger_release"),
        )
        with (
            patch("vibemouse.mouse_listener.time.monotonic", return_value=100.5),
            patch.object(listener, "_end_button_suppress") as end_suppress,
        ):
            should_replay, gesture_direction = consume()

        self.assertFalse(should_replay)
        self.assertIsNone(gesture_direction)
        end_suppress.assert_called_once_with(button_label="right")
        self.assertFalse(cast(bool, getattr(listener, "_right_trigger_pressed")))


    def test_right_trigger_dispatches_gesture_after_large_move(self) -> None:
        class _FakeEvent:
            def __init__(self, event_type: int, code: int, value: int) -> None:
                self.type = event_type
                self.code = code
                self.value = value

        class _FakeDevice:
            def __init__(self, events: list[_FakeEvent], key_cap: list[int]) -> None:
                self.fd = 90
                self._events = events
                self._key_cap = key_cap

            def capabilities(self) -> dict[int, list[int]]:
                return {1: self._key_cap}

            def read(self) -> list[_FakeEvent]:
                events = self._events
                self._events = []
                return events

            def close(self) -> None:
                return

        right_code = 273
        rel_x = 0
        events = [
            _FakeEvent(1, right_code, 1),
            _FakeEvent(2, rel_x, 160),
            _FakeEvent(1, right_code, 0),
        ]
        fake_device = _FakeDevice(events=events, key_cap=[272, 273, 275, 276])

        fake_ecodes = type(
            "_Ecodes",
            (),
            {
                "BTN_SIDE": 275,
                "BTN_EXTRA": 276,
                "BTN_BACK": 278,
                "BTN_FORWARD": 277,
                "BTN_LEFT": 272,
                "BTN_RIGHT": right_code,
                "EV_KEY": 1,
                "EV_REL": 2,
                "REL_X": rel_x,
                "REL_Y": 1,
            },
        )
        fake_module = type(
            "_EvdevModule",
            (),
            {
                "InputDevice": lambda _path: fake_device,
                "ecodes": fake_ecodes,
                "list_devices": lambda: ["/dev/input/event-right-move"],
            },
        )

        listener = SideButtonListener(
            on_front_press=lambda: None,
            on_rear_press=lambda: None,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
            system_integration=_NeutralSystemIntegration(),
        )

        def _import_module(name: str):
            if name == "evdev":
                return fake_module
            return _real_import_module(name)

        timeline: list[str] = []

        def _mark_begin(*, source_device: object, button_label: str) -> None:
            self.assertIs(source_device, fake_device)
            self.assertEqual(button_label, "right")
            setattr(listener, "_button_grabbed_label", "right")
            timeline.append("begin")

        def _mark_end(*, button_label: str) -> None:
            self.assertEqual(button_label, "right")
            timeline.append("end")

        def _mark_gesture(direction: str) -> None:
            self.assertEqual(direction, "right")
            timeline.append("gesture")
            listener._stop.set()

        with (
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                side_effect=_import_module,
            ),
            patch("select.select", return_value=([90], [], [])),
            patch.object(
                listener,
                "_begin_button_suppress",
                side_effect=_mark_begin,
            ),
            patch.object(listener, "_end_button_suppress", side_effect=_mark_end),
            patch.object(listener, "_dispatch_gesture", side_effect=_mark_gesture),
            patch.object(listener, "_dispatch_click_async") as dispatch_click_async,
            patch.object(listener, "_start_gesture_capture") as start_capture,
            patch.object(listener, "_finish_gesture_capture") as finish_capture,
        ):
            run_evdev = cast(Callable[[], None], getattr(listener, "_run_evdev"))
            run_evdev()

        self.assertEqual(timeline, ["begin", "end", "gesture"])
        dispatch_click_async.assert_not_called()
        start_capture.assert_not_called()
        finish_capture.assert_not_called()


    def test_front_click_path_does_not_use_button_suppress_grab(self) -> None:
        class _FakeEvent:
            def __init__(self, event_type: int, code: int, value: int) -> None:
                self.type = event_type
                self.code = code
                self.value = value

        class _FakeDevice:
            def __init__(self, events: list[_FakeEvent], key_cap: list[int]) -> None:
                self.fd = 66
                self._events = events
                self._key_cap = key_cap

            def capabilities(self) -> dict[int, list[int]]:
                return {1: self._key_cap}

            def read(self) -> list[_FakeEvent]:
                events = self._events
                self._events = []
                return events

            def close(self) -> None:
                return

        front_code = 275
        events = [_FakeEvent(1, front_code, 1), _FakeEvent(1, front_code, 0)]
        fake_device = _FakeDevice(events=events, key_cap=[272, 273, 275, 276])
        callbacks: list[str] = []

        def _on_front() -> None:
            callbacks.append("front")
            listener._stop.set()

        listener = SideButtonListener(
            on_front_press=_on_front,
            on_rear_press=lambda: None,
            front_button="x1",
            rear_button="x2",
        )

        fake_ecodes = type(
            "_Ecodes",
            (),
            {
                "BTN_SIDE": front_code,
                "BTN_EXTRA": 276,
                "BTN_BACK": 278,
                "BTN_FORWARD": 277,
                "BTN_LEFT": 272,
                "BTN_RIGHT": 273,
                "EV_KEY": 1,
                "EV_REL": 2,
                "REL_X": 0,
                "REL_Y": 1,
            },
        )
        fake_module = type(
            "_EvdevModule",
            (),
            {
                "InputDevice": lambda _path: fake_device,
                "ecodes": fake_ecodes,
                "list_devices": lambda: ["/dev/input/event-front"],
            },
        )

        def _import_module(name: str):
            if name == "evdev":
                return fake_module
            return _real_import_module(name)

        with (
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                side_effect=_import_module,
            ),
            patch("select.select", return_value=([66], [], [])),
            patch.object(listener, "_begin_button_suppress") as begin_suppress,
            patch.object(listener, "_end_button_suppress") as end_suppress,
        ):
            run_evdev = cast(Callable[[], None], getattr(listener, "_run_evdev"))
            run_evdev()

        self.assertEqual(callbacks, ["front"])
        begin_suppress.assert_not_called()
        end_suppress.assert_not_called()

    def test_pynput_ignores_right_click_when_not_right_trigger(self) -> None:
        class _FakeButton:
            def __init__(self, name: str) -> None:
                self._name = name

            def __str__(self) -> str:
                return f"Button.{self._name}"

        class _FakeMouseListener:
            def __init__(
                self,
                *,
                on_click: Callable[[int, int, object, bool], None],
                on_move: Callable[[int, int], None],
            ) -> None:
                self._on_click = on_click
                self._on_move = on_move

            def start(self) -> None:
                self._on_click(10, 20, fake_button_holder.right, True)
                self._on_click(10, 20, fake_button_holder.right, False)

            def stop(self) -> None:
                return

        fake_button_holder = type("_FakeButtonHolder", (), {"right": _FakeButton("right")})

        def _listener_ctor(
            *, on_click: Callable[[int, int, object, bool], None], on_move: Callable[[int, int], None]
        ) -> _FakeMouseListener:
            return _FakeMouseListener(on_click=on_click, on_move=on_move)

        fake_mouse_module = type(
            "_FakeMouseModule",
            (),
            {
                "Listener": _listener_ctor,
                "Button": fake_button_holder,
            },
        )

        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="rear",
            system_integration=_NeutralSystemIntegration(),
        )

        def _import_module(name: str):
            if name == "pynput.mouse":
                return fake_mouse_module
            return _real_import_module(name)

        with (
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                side_effect=_import_module,
            ),
            patch.object(listener, "_dispatch_click_async") as dispatch_click_async,
        ):
            listener._run_pynput(timeout_s=0.2)

        dispatch_click_async.assert_not_called()


class _GrabDeviceStub:
    def __init__(self, *, fail_ungrab_times: int = 0) -> None:
        self.grab_calls = 0
        self.ungrab_calls = 0
        self._remaining_ungrab_failures = fail_ungrab_times

    def grab(self) -> None:
        self.grab_calls += 1

    def ungrab(self) -> None:
        self.ungrab_calls += 1
        if self._remaining_ungrab_failures > 0:
            self._remaining_ungrab_failures -= 1
            raise OSError("temporary ungrab failure")
