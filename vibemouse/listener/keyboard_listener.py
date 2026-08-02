from __future__ import annotations

import importlib
import select
import sys
import threading
import time
from collections.abc import Callable
from typing import Protocol, cast


HotkeyCallback = Callable[[], None]
EventCallback = Callable[[str], None]


class KeyboardHotkeyListener:
    def __init__(
        self,
        *,
        keycodes: tuple[int, ...],
        on_hotkey: HotkeyCallback | None = None,
        on_event: EventCallback | None = None,
        event_name: str | None = None,
        debounce_s: float = 0.15,
        rescan_interval_s: float = 2.0,
    ) -> None:
        if not keycodes:
            raise ValueError("keycodes must not be empty")
        if on_hotkey is None and (on_event is None or not event_name):
            raise ValueError(
                "on_hotkey or on_event/event_name must be configured"
            )
        self._on_hotkey: HotkeyCallback | None = on_hotkey
        self._on_event: EventCallback | None = on_event
        self._event_name: str | None = event_name
        self._combo: frozenset[int] = frozenset(
            self._normalize_configured_keycode(code) for code in keycodes
        )
        self._debounce_s: float = max(0.0, debounce_s)
        self._rescan_interval_s: float = max(0.2, rescan_interval_s)
        self._state_lock: threading.Lock = threading.Lock()
        self._pressed: set[int] = set()
        self._combo_latched: bool = False
        self._last_fire_monotonic: float = 0.0
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        last_error_summary: str | None = None
        while not self._stop.is_set():
            try:
                if sys.platform.startswith("win"):
                    self._run_pynput(timeout_s=self._rescan_interval_s)
                else:
                    self._run_evdev()
                self._reset_pressed_state()
                continue
            except Exception as error:
                summary = f"Keyboard hotkey listener unavailable ({error}). Retrying..."
                if summary != last_error_summary:
                    print(summary)
                    last_error_summary = summary
                self._reset_pressed_state()
                if self._stop.wait(1.0):
                    return

    def _run_evdev(self) -> None:
        try:
            evdev_module = importlib.import_module("evdev")
        except Exception as error:
            raise RuntimeError("evdev is not available") from error

        input_device_ctor = cast(_InputDeviceCtor, getattr(evdev_module, "InputDevice"))
        ecodes = cast(_Ecodes, getattr(evdev_module, "ecodes"))
        list_devices = cast(_ListDevicesFn, getattr(evdev_module, "list_devices"))

        devices: list[_EvdevDevice] = []
        for path in list_devices():
            try:
                dev = input_device_ctor(path)
            except Exception:
                continue
            try:
                caps = dev.capabilities()
                key_cap = caps.get(ecodes.EV_KEY, [])
                normalized_caps = {
                    self._normalize_configured_keycode(int(code)) for code in key_cap
                }
                if not any(code in normalized_caps for code in self._combo):
                    dev.close()
                    continue
                if ecodes.KEY_A not in key_cap:
                    dev.close()
                    continue
                devices.append(dev)
            except Exception:
                dev.close()

        if not devices:
            raise RuntimeError("No keyboard input device with required keycodes found")

        try:
            fd_map: dict[int, _EvdevDevice] = {dev.fd: dev for dev in devices}
            next_rescan_at = time.monotonic() + self._rescan_interval_s
            while not self._stop.is_set():
                if not fd_map:
                    return
                now = time.monotonic()
                if now >= next_rescan_at:
                    return

                timeout_s = min(0.2, max(0.0, next_rescan_at - now))
                try:
                    ready, _, _ = select.select(list(fd_map.keys()), [], [], timeout_s)
                except (OSError, ValueError):
                    return
                for fd in ready:
                    dev = fd_map[fd]
                    try:
                        events = dev.read()
                    except OSError:
                        return
                    for event in events:
                        if event.type != ecodes.EV_KEY:
                            continue
                        if self._process_key_event(event.code, event.value):
                            self._dispatch_hotkey()
        finally:
            for dev in devices:
                dev.close()

    def _run_pynput(self, *, timeout_s: float | None = None) -> None:
        try:
            keyboard_module = importlib.import_module("pynput.keyboard")
        except Exception as error:
            raise RuntimeError("pynput.keyboard is not available") from error

        listener_ctor = cast(_KeyboardListenerCtor, getattr(keyboard_module, "Listener"))

        def on_press(key: object) -> None:
            keycode = self._extract_windows_keycode(key)
            if keycode is None:
                return
            if self._process_key_event(keycode, 1):
                self._dispatch_hotkey()

        def on_release(key: object) -> None:
            keycode = self._extract_windows_keycode(key)
            if keycode is None:
                return
            _ = self._process_key_event(keycode, 0)

        listener = listener_ctor(on_press=on_press, on_release=on_release)
        listener.start()
        deadline: float | None = None
        if timeout_s is not None:
            deadline = time.monotonic() + max(0.2, timeout_s)
        try:
            while not self._stop.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    return
                time.sleep(0.2)
        finally:
            listener.stop()

    def _reset_pressed_state(self) -> None:
        with self._state_lock:
            self._pressed.clear()
            self._combo_latched = False

    def _process_key_event(self, keycode: int, value: int) -> bool:
        normalized = self._normalize_runtime_keycode(keycode)
        with self._state_lock:
            if value == 1:
                self._pressed.add(normalized)
            elif value == 0:
                self._pressed.discard(normalized)
            else:
                return False

            if self._combo_latched and not self._combo.issubset(self._pressed):
                self._combo_latched = False

            now = time.monotonic()
            if (
                not self._combo_latched
                and self._combo.issubset(self._pressed)
                and now - self._last_fire_monotonic >= self._debounce_s
            ):
                self._combo_latched = True
                self._last_fire_monotonic = now
                return True
            return False

    @classmethod
    def _normalize_configured_keycode(cls, keycode: int) -> int:
        return cls._normalize_windows_vk(keycode)

    @classmethod
    def _normalize_runtime_keycode(cls, keycode: int) -> int:
        return cls._normalize_windows_vk(keycode)

    @staticmethod
    def _normalize_windows_vk(keycode: int) -> int:
        mapping = {
            160: 16,
            161: 16,
            162: 17,
            163: 17,
            164: 18,
            165: 18,
            92: 91,
        }
        return mapping.get(int(keycode), int(keycode))

    @classmethod
    def _extract_windows_keycode(cls, key: object) -> int | None:
        vk = getattr(key, "vk", None)
        if isinstance(vk, int):
            return cls._normalize_windows_vk(vk)
        value = getattr(key, "value", None)
        nested_vk = getattr(value, "vk", None)
        if isinstance(nested_vk, int):
            return cls._normalize_windows_vk(nested_vk)
        char = getattr(key, "char", None)
        if isinstance(char, str) and len(char) == 1:
            return ord(char.upper())
        return None

    def _dispatch_hotkey(self) -> None:
        event_name = self._event_name
        if self._on_event is not None and isinstance(event_name, str) and event_name:
            self._on_event(event_name)
            return
        callback = self._on_hotkey
        if callback is not None:
            callback()


class _EvdevEvent(Protocol):
    type: int
    value: int
    code: int


class _EvdevDevice(Protocol):
    fd: int

    def read(self) -> list[_EvdevEvent]: ...

    def capabilities(self) -> dict[int, list[int]]: ...

    def close(self) -> None: ...


class _InputDeviceCtor(Protocol):
    def __call__(self, path: str) -> _EvdevDevice: ...


class _ListDevicesFn(Protocol):
    def __call__(self) -> list[str]: ...


class _Ecodes(Protocol):
    EV_KEY: int
    KEY_A: int


class _KeyboardListener(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class _KeyboardListenerCtor(Protocol):
    def __call__(
        self,
        *,
        on_press: Callable[[object], None] | None = None,
        on_release: Callable[[object], None] | None = None,
    ) -> _KeyboardListener: ...
