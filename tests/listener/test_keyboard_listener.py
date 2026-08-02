from __future__ import annotations

import unittest
from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

from vibemouse.core.commands import EVENT_HOTKEY_RECORD_TOGGLE
from vibemouse.keyboard_listener import KeyboardHotkeyListener


def _noop() -> None:
    return


class KeyboardHotkeyListenerTests(unittest.TestCase):
    def test_constructor_rejects_empty_combo(self) -> None:
        with self.assertRaisesRegex(ValueError, "keycodes must not be empty"):
            _ = KeyboardHotkeyListener(on_hotkey=_noop, keycodes=())

    def test_constructor_requires_callback_or_event(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "on_hotkey or on_event/event_name must be configured",
        ):
            _ = KeyboardHotkeyListener(keycodes=(42, 125, 193))

    def test_combo_fires_once_until_released(self) -> None:
        listener = KeyboardHotkeyListener(
            on_hotkey=_noop, keycodes=(42, 125, 193), debounce_s=0.0
        )
        process = cast(
            Callable[[int, int], bool], getattr(listener, "_process_key_event")
        )

        self.assertFalse(process(42, 1))
        self.assertFalse(process(125, 1))
        self.assertTrue(process(193, 1))
        self.assertFalse(process(193, 1))
        self.assertFalse(process(42, 0))
        self.assertTrue(process(42, 1))

    def test_repeat_events_do_not_trigger(self) -> None:
        listener = KeyboardHotkeyListener(
            on_hotkey=_noop, keycodes=(42, 125, 193), debounce_s=0.0
        )
        process = cast(
            Callable[[int, int], bool], getattr(listener, "_process_key_event")
        )

        self.assertFalse(process(42, 1))
        self.assertFalse(process(125, 1))
        self.assertFalse(process(193, 2))
        self.assertTrue(process(193, 1))

    def test_reset_pressed_state_clears_latched_combo(self) -> None:
        listener = KeyboardHotkeyListener(
            on_hotkey=_noop, keycodes=(42, 125, 193), debounce_s=0.0
        )
        process = cast(
            Callable[[int, int], bool], getattr(listener, "_process_key_event")
        )
        reset = cast(Callable[[], None], getattr(listener, "_reset_pressed_state"))

        self.assertFalse(process(42, 1))
        self.assertFalse(process(125, 1))
        self.assertTrue(process(193, 1))
        reset()
        self.assertFalse(process(42, 1))
        self.assertFalse(process(125, 1))
        self.assertTrue(process(193, 1))

    def test_dispatch_hotkey_emits_configured_event(self) -> None:
        seen: list[str] = []
        listener = KeyboardHotkeyListener(
            on_event=seen.append,
            event_name=EVENT_HOTKEY_RECORD_TOGGLE,
            keycodes=(42, 125, 193),
            debounce_s=0.0,
        )

        dispatch = cast(Callable[[], None], getattr(listener, "_dispatch_hotkey"))
        dispatch()

        self.assertEqual(seen, [EVENT_HOTKEY_RECORD_TOGGLE])

    def test_windows_modifier_keycodes_are_normalized(self) -> None:
        listener = KeyboardHotkeyListener(
            on_hotkey=_noop, keycodes=(16, 91, 134), debounce_s=0.0
        )
        process = cast(
            Callable[[int, int], bool], getattr(listener, "_process_key_event")
        )

        self.assertFalse(process(160, 1))
        self.assertFalse(process(92, 1))
        self.assertTrue(process(134, 1))

    def test_extract_windows_keycode_prefers_vk_attribute(self) -> None:
        extract = cast(
            Callable[[object], int | None],
            getattr(KeyboardHotkeyListener, "_extract_windows_keycode"),
        )
        self.assertEqual(extract(SimpleNamespace(vk=160)), 16)
