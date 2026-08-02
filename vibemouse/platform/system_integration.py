from __future__ import annotations

import ctypes
import importlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from ctypes import wintypes


_TERMINAL_CLASS_HINTS: set[str] = {
    "foot",
    "kitty",
    "alacritty",
    "wezterm",
    "ghostty",
    "gnome-terminal",
    "gnome-terminal-server",
    "konsole",
    "tilix",
    "xterm",
    "terminator",
    "xfce4-terminal",
    "urxvt",
    "st",
    "tabby",
    "hyper",
    "warp",
    "windowsterminal",
    "wt",
    "cascadia_hosting_window_class",
    "consolewindowclass",
    "mintty",
}

_TERMINAL_TITLE_HINTS: set[str] = {
    "terminal",
    "tmux",
    "bash",
    "zsh",
    "fish",
    "powershell",
    "cmd.exe",
    "pwsh",
}

_BROWSER_CLASS_HINTS: set[str] = {
    "firefox",
    "zen",
    "librewolf",
    "waterfox",
    "floorp",
    "chromium",
    "google-chrome",
    "chrome",
    "brave-browser",
    "microsoft-edge",
    "vivaldi",
    "opera",
    "thorium",
    "browser",
    "chrome_widgetwin_1",
    "mozillawindowclass",
}

_WINDOWS_TEXT_CONTROL_CLASSES: set[str] = {
    "edit",
    "richedit20a",
    "richedit20w",
    "richedit50w",
    "scintilla",
    "consolewindowclass",
    "cascadia_hosting_window_class",
}


if sys.platform.startswith("win"):
    _USER32 = ctypes.WinDLL("user32", use_last_error=True)
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:
    _USER32 = None
    _KERNEL32 = None


class _Point(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", _Rect),
    ]


if _USER32 is not None and _KERNEL32 is not None:
    _USER32.GetForegroundWindow.restype = wintypes.HWND
    _USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _USER32.GetWindowTextLengthW.restype = ctypes.c_int
    _USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _USER32.GetWindowTextW.restype = ctypes.c_int
    _USER32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _USER32.GetClassNameW.restype = ctypes.c_int
    _USER32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _USER32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _USER32.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
    _USER32.GetCursorPos.restype = wintypes.BOOL
    _USER32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _USER32.SetCursorPos.restype = wintypes.BOOL
    _USER32.GetGUIThreadInfo.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(_GuiThreadInfo),
    ]
    _USER32.GetGUIThreadInfo.restype = wintypes.BOOL

    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _KERNEL32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL


def is_terminal_window_payload(payload: Mapping[str, object]) -> bool:
    window_class = str(payload.get("class", "")).lower()
    initial_class = str(payload.get("initialClass", "")).lower()
    title = str(payload.get("title", "")).lower()
    process = str(payload.get("process", "")).lower()

    if any(
        hint in window_class or hint in initial_class or hint in process
        for hint in _TERMINAL_CLASS_HINTS
    ):
        return True

    return any(hint in title for hint in _TERMINAL_TITLE_HINTS)


def is_browser_window_payload(payload: Mapping[str, object]) -> bool:
    window_class = str(payload.get("class", "")).lower()
    initial_class = str(payload.get("initialClass", "")).lower()
    title = str(payload.get("title", "")).lower()
    process = str(payload.get("process", "")).lower()

    if any(
        hint in window_class or hint in initial_class or hint in process
        for hint in _BROWSER_CLASS_HINTS
    ):
        return True

    return "browser" in title or "chrome" in title or "firefox" in title


class SystemIntegration(Protocol):
    @property
    def is_hyprland(self) -> bool: ...

    def send_shortcut(self, *, mod: str, key: str) -> bool: ...

    def active_window(self) -> dict[str, object] | None: ...

    def cursor_position(self) -> tuple[int, int] | None: ...

    def move_cursor(self, *, x: int, y: int) -> bool: ...

    def switch_workspace(self, direction: str) -> bool: ...

    def is_text_input_focused(self) -> bool | None: ...

    def send_enter_via_accessibility(self) -> bool | None: ...

    def is_terminal_window_active(self) -> bool | None: ...

    def paste_shortcuts(
        self, *, terminal_active: bool
    ) -> tuple[tuple[str, str], ...]: ...


class NoopSystemIntegration:
    @property
    def is_hyprland(self) -> bool:
        return False

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        del mod
        del key
        return False

    def active_window(self) -> dict[str, object] | None:
        return None

    def cursor_position(self) -> tuple[int, int] | None:
        return None

    def move_cursor(self, *, x: int, y: int) -> bool:
        del x
        del y
        return False

    def switch_workspace(self, direction: str) -> bool:
        del direction
        return False

    def is_text_input_focused(self) -> bool | None:
        return None

    def send_enter_via_accessibility(self) -> bool | None:
        return None

    def is_terminal_window_active(self) -> bool | None:
        return None

    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        del terminal_active
        return ()


class WindowsSystemIntegration:
    def __init__(self) -> None:
        self._shortcut_controller: object | None = None
        self._shortcut_keys: object | None = None

    @property
    def is_hyprland(self) -> bool:
        return False

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        controller, key_holder = self._load_keyboard_backend()
        if controller is None or key_holder is None:
            return False

        modifiers: list[object] = []
        for token in mod.strip().upper().split():
            if not token:
                continue
            resolved = self._resolve_modifier(token, key_holder)
            if resolved is None:
                return False
            modifiers.append(resolved)

        target = self._resolve_key(key, key_holder)
        if target is None:
            return False

        pressed: list[object] = []
        try:
            for item in modifiers:
                controller.press(item)
                pressed.append(item)
            controller.press(target)
            pressed.append(target)
            time.sleep(0.012)
            return True
        except Exception:
            return False
        finally:
            for item in reversed(pressed):
                try:
                    controller.release(item)
                except Exception:
                    pass

    def active_window(self) -> dict[str, object] | None:
        hwnd = self._foreground_window_handle()
        if hwnd is None:
            return None

        pid = self._window_process_id(hwnd)
        payload: dict[str, object] = {
            "class": self._window_class_name(hwnd),
            "initialClass": self._window_class_name(hwnd),
            "title": self._window_title(hwnd),
        }
        if pid is not None:
            payload["pid"] = pid
        process_name = self._process_name(pid)
        if process_name:
            payload["process"] = process_name
        return payload

    def cursor_position(self) -> tuple[int, int] | None:
        if _USER32 is None:
            return None
        point = _Point()
        if not bool(_USER32.GetCursorPos(ctypes.byref(point))):
            return None
        return point.x, point.y

    def move_cursor(self, *, x: int, y: int) -> bool:
        if _USER32 is None:
            return False
        return bool(_USER32.SetCursorPos(int(x), int(y)))

    def switch_workspace(self, direction: str) -> bool:
        key = "Left" if direction == "left" else "Right"
        return self.send_shortcut(mod="CTRL WIN", key=key)

    def is_text_input_focused(self) -> bool | None:
        focus_hwnd = self._focused_window_handle()
        if focus_hwnd is None:
            return None

        class_name = self._window_class_name(focus_hwnd).lower()
        payload = {
            "class": class_name,
            "initialClass": class_name,
            "title": self._window_title(focus_hwnd).lower(),
        }
        if is_terminal_window_payload(payload):
            return True
        if class_name in _WINDOWS_TEXT_CONTROL_CLASSES:
            return True
        return "edit" in class_name or "textarea" in class_name

    def send_enter_via_accessibility(self) -> bool | None:
        return None

    def is_terminal_window_active(self) -> bool | None:
        payload = self.active_window()
        if payload is None:
            return False
        return is_terminal_window_payload(payload)

    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        if terminal_active:
            return (
                ("CTRL SHIFT", "V"),
                ("SHIFT", "Insert"),
                ("CTRL", "V"),
            )
        return (("CTRL", "V"),)

    def _load_keyboard_backend(self) -> tuple[object | None, object | None]:
        if self._shortcut_controller is not None and self._shortcut_keys is not None:
            return self._shortcut_controller, self._shortcut_keys

        try:
            keyboard_module = importlib.import_module("pynput.keyboard")
        except Exception:
            return None, None

        controller_ctor = getattr(keyboard_module, "Controller", None)
        key_holder = getattr(keyboard_module, "Key", None)
        if controller_ctor is None or key_holder is None:
            return None, None

        try:
            controller = controller_ctor()
        except Exception:
            return None, None

        self._shortcut_controller = cast(object, controller)
        self._shortcut_keys = cast(object, key_holder)
        return self._shortcut_controller, self._shortcut_keys

    @staticmethod
    def _resolve_modifier(token: str, key_holder: object) -> object | None:
        mapping = {
            "CTRL": "ctrl",
            "CONTROL": "ctrl",
            "SHIFT": "shift",
            "ALT": "alt",
            "WIN": "cmd",
            "META": "cmd",
            "CMD": "cmd",
            "SUPER": "cmd",
        }
        attr = mapping.get(token)
        if attr is None:
            return None
        return getattr(key_holder, attr, None)

    @staticmethod
    def _resolve_key(raw_key: str, key_holder: object) -> object | None:
        normalized = raw_key.strip().upper()
        special_mapping = {
            "RETURN": "enter",
            "ENTER": "enter",
            "INSERT": "insert",
            "LEFT": "left",
            "RIGHT": "right",
            "UP": "up",
            "DOWN": "down",
            "TAB": "tab",
            "ESC": "esc",
            "ESCAPE": "esc",
            "SPACE": "space",
        }
        attr = special_mapping.get(normalized)
        if attr is not None:
            return getattr(key_holder, attr, None)

        if len(normalized) == 1:
            return normalized.lower()

        if normalized.startswith("F") and normalized[1:].isdigit():
            return getattr(key_holder, normalized.lower(), None)

        return None

    @staticmethod
    def _foreground_window_handle() -> int | None:
        if _USER32 is None:
            return None
        hwnd = _USER32.GetForegroundWindow()
        return int(hwnd) if hwnd else None

    @staticmethod
    def _window_title(hwnd: int) -> str:
        if _USER32 is None:
            return ""
        length = int(_USER32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        _ = _USER32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    @staticmethod
    def _window_class_name(hwnd: int) -> str:
        if _USER32 is None:
            return ""
        buffer = ctypes.create_unicode_buffer(256)
        copied = int(_USER32.GetClassNameW(hwnd, buffer, len(buffer)))
        if copied <= 0:
            return ""
        return buffer.value

    @staticmethod
    def _window_process_id(hwnd: int | None) -> int | None:
        if _USER32 is None or hwnd is None:
            return None
        pid = wintypes.DWORD(0)
        _ = _USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None

    @staticmethod
    def _process_name(pid: int | None) -> str | None:
        if _KERNEL32 is None or pid is None:
            return None

        process_handle = _KERNEL32.OpenProcess(0x1000, False, pid)
        if not process_handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            ok = bool(
                _KERNEL32.QueryFullProcessImageNameW(
                    process_handle,
                    0,
                    buffer,
                    ctypes.byref(size),
                )
            )
            if not ok:
                return None
            return Path(buffer.value).name
        finally:
            _ = _KERNEL32.CloseHandle(process_handle)

    def _focused_window_handle(self) -> int | None:
        hwnd = self._foreground_window_handle()
        if hwnd is None or _USER32 is None:
            return hwnd

        thread_id = _USER32.GetWindowThreadProcessId(hwnd, None)
        if not thread_id:
            return hwnd

        info = _GuiThreadInfo()
        info.cbSize = ctypes.sizeof(_GuiThreadInfo)
        if not bool(_USER32.GetGUIThreadInfo(thread_id, ctypes.byref(info))):
            return hwnd

        focus_hwnd = info.hwndFocus or info.hwndActive
        return int(focus_hwnd) if focus_hwnd else hwnd


class HyprlandSystemIntegration:
    @property
    def is_hyprland(self) -> bool:
        return True

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        mod_part = mod.strip().upper()
        if mod_part:
            arg = f"{mod_part}, {key}, activewindow"
        else:
            arg = f", {key}, activewindow"
        return self._dispatch(["sendshortcut", arg], timeout=1.0)

    def active_window(self) -> dict[str, object] | None:
        return self._query_json(["activewindow"], timeout=1.0)

    def cursor_position(self) -> tuple[int, int] | None:
        payload = self._query_json(["cursorpos"], timeout=0.8)
        if payload is None:
            return None

        x_raw = payload.get("x")
        y_raw = payload.get("y")
        if not isinstance(x_raw, int | float) or not isinstance(y_raw, int | float):
            return None

        return int(x_raw), int(y_raw)

    def move_cursor(self, *, x: int, y: int) -> bool:
        return self._dispatch(["movecursor", str(x), str(y)], timeout=0.8)

    def switch_workspace(self, direction: str) -> bool:
        workspace_arg = "e-1" if direction == "left" else "e+1"
        return self._dispatch(["workspace", workspace_arg], timeout=1.0)

    def is_text_input_focused(self) -> bool | None:
        return probe_text_input_focus_via_atspi()

    def send_enter_via_accessibility(self) -> bool | None:
        return probe_send_enter_via_atspi()

    def is_terminal_window_active(self) -> bool | None:
        payload = self.active_window()
        if payload is None:
            return False
        return is_terminal_window_payload(payload)

    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        if terminal_active:
            return (
                ("CTRL SHIFT", "V"),
                ("SHIFT", "Insert"),
                ("CTRL", "V"),
            )
        return (("CTRL", "V"),)

    @staticmethod
    def _dispatch(args: list[str], *, timeout: float) -> bool:
        try:
            proc = subprocess.run(
                ["hyprctl", "dispatch", *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return proc.returncode == 0 and proc.stdout.strip() == "ok"

    @staticmethod
    def _query_json(args: list[str], *, timeout: float) -> dict[str, object] | None:
        try:
            proc = subprocess.run(
                ["hyprctl", "-j", *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if proc.returncode != 0:
            return None

        try:
            payload_obj = cast(object, json.loads(proc.stdout))
        except json.JSONDecodeError:
            return None

        if not isinstance(payload_obj, dict):
            return None

        return cast(dict[str, object], payload_obj)


def detect_hyprland_session(*, env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    desktop = source.get("XDG_CURRENT_DESKTOP", "")
    if "hyprland" in desktop.lower():
        return True
    return bool(source.get("HYPRLAND_INSTANCE_SIGNATURE"))


def create_system_integration(
    *,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> SystemIntegration:
    if detect_hyprland_session(env=env):
        return HyprlandSystemIntegration()

    normalized_platform = platform_name if platform_name is not None else sys.platform
    if normalized_platform.startswith("win"):
        return WindowsSystemIntegration()

    return NoopSystemIntegration()


def probe_text_input_focus_via_atspi(*, timeout_s: float = 1.5) -> bool:
    if not sys.platform.startswith("linux"):
        return False

    script = (
        "import gi\n"
        "gi.require_version('Atspi', '2.0')\n"
        "from gi.repository import Atspi\n"
        "obj = Atspi.get_desktop(0).get_focus()\n"
        "editable = False\n"
        "role = ''\n"
        "if obj is not None:\n"
        "    role = obj.get_role_name().lower()\n"
        "    attrs = obj.get_attributes() or []\n"
        "    for it in attrs:\n"
        "        s = str(it).lower()\n"
        "        if s == 'editable:true' or s.endswith(':editable:true'):\n"
        "            editable = True\n"
        "            break\n"
        "roles = {'text', 'entry', 'password text', 'terminal', 'paragraph', 'document text', 'document web'}\n"
        "print('1' if editable or role in roles else '0')\n"
    )

    try:
        proc = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return proc.returncode == 0 and proc.stdout.strip() == "1"


def load_atspi_module() -> object | None:
    if not sys.platform.startswith("linux"):
        return None

    try:
        gi = importlib.import_module("gi")
        require_version = cast(_RequireVersionFn, getattr(gi, "require_version"))
        require_version("Atspi", "2.0")
        atspi_repo = cast(object, importlib.import_module("gi.repository"))
        return cast(object, getattr(atspi_repo, "Atspi"))
    except Exception:
        return None


def probe_send_enter_via_atspi(
    *, atspi_module: object | None = None, lazy_load: bool = True
) -> bool:
    module = atspi_module
    if module is None and lazy_load:
        module = load_atspi_module()
    if module is None:
        return False

    try:
        key_synth = cast(object, getattr(module, "KeySynthType"))
        press_release = cast(object, getattr(key_synth, "PRESSRELEASE"))
        generate_keyboard_event = cast(
            _GenerateKeyboardEventFn,
            getattr(module, "generate_keyboard_event"),
        )
        return bool(generate_keyboard_event(65293, None, press_release))
    except Exception:
        return False


class _GenerateKeyboardEventFn(Protocol):
    def __call__(
        self,
        keyval: int,
        keystring: str | None,
        synth_type: object,
    ) -> bool: ...


class _RequireVersionFn(Protocol):
    def __call__(self, namespace: str, version: str) -> None: ...
