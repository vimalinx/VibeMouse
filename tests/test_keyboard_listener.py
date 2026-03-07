from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import cast

from vibemouse.keyboard_listener import KeyboardHotkeyListener


def _noop() -> None:
    return


class KeyboardHotkeyListenerTests(unittest.TestCase):
    def test_constructor_rejects_empty_combo(self) -> None:
        with self.assertRaisesRegex(ValueError, "keycodes must not be empty"):
            _ = KeyboardHotkeyListener(on_hotkey=_noop, keycodes=())

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
