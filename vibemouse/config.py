from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a float, got {raw!r}") from error


def _read_button(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in {"x1", "x2"}:
        raise ValueError(f"{name} must be either 'x1' or 'x2', got {value!r}")
    return value


def _require_positive(name: str, value: int) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value}")
    return value


def _require_non_negative(name: str, value: int) -> int:
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value}")
    return value


def _require_positive_float(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be a positive float, got {value}")
    return value


def _require_non_negative_float(name: str, value: float) -> float:
    if value < 0:
        raise ValueError(f"{name} must be a non-negative float, got {value}")
    return value


def _read_choice(name: str, default: str, allowed: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {options}; got {value!r}")
    return value


@dataclass(frozen=True)
class AppConfig:
    sample_rate: int
    channels: int
    dtype: str
    transcriber_backend: str
    model_name: str
    log_level: str
    device: str
    language: str
    use_itn: bool
    enable_vad: bool
    vad_max_single_segment_ms: int
    merge_vad: bool
    merge_length_s: int
    fallback_to_cpu: bool
    button_debounce_ms: int
    gestures_enabled: bool
    gesture_trigger_button: str
    gesture_threshold_px: int
    gesture_freeze_pointer: bool
    gesture_restore_cursor: bool
    gesture_up_action: str
    gesture_down_action: str
    gesture_left_action: str
    gesture_right_action: str
    enter_mode: str
    auto_paste: bool
    trust_remote_code: bool
    prewarm_on_start: bool
    prewarm_delay_s: float
    status_file: Path
    openclaw_command: str
    openclaw_agent: str | None
    openclaw_timeout_s: float
    openclaw_retries: int
    front_button: str
    rear_button: str
    record_hotkey_keycodes: tuple[int, ...]
    temp_dir: Path


def load_config() -> AppConfig:
    temp_dir = Path(
        os.getenv("VIBEMOUSE_TEMP_DIR", str(Path(tempfile.gettempdir()) / "vibemouse"))
    )
    runtime_dir = Path(os.getenv("XDG_RUNTIME_DIR", tempfile.gettempdir()))
    status_file = Path(
        os.getenv("VIBEMOUSE_STATUS_FILE", str(runtime_dir / "vibemouse-status.json"))
    )

    sample_rate = _require_positive(
        "VIBEMOUSE_SAMPLE_RATE", _read_int("VIBEMOUSE_SAMPLE_RATE", 16000)
    )
    channels = _require_positive(
        "VIBEMOUSE_CHANNELS", _read_int("VIBEMOUSE_CHANNELS", 1)
    )
    vad_max_segment_ms = _require_positive(
        "VIBEMOUSE_VAD_MAX_SEGMENT_MS", _read_int("VIBEMOUSE_VAD_MAX_SEGMENT_MS", 30000)
    )
    merge_length_s = _require_positive(
        "VIBEMOUSE_MERGE_LENGTH_S", _read_int("VIBEMOUSE_MERGE_LENGTH_S", 15)
    )
    front_button = _read_button("VIBEMOUSE_FRONT_BUTTON", "x1")
    rear_button = _read_button("VIBEMOUSE_REAR_BUTTON", "x2")
    record_hotkey_keycodes = tuple(
        sorted(
            {
                _require_non_negative(
                    "VIBEMOUSE_RECORD_HOTKEY_CODE_1",
                    _read_int("VIBEMOUSE_RECORD_HOTKEY_CODE_1", 42),
                ),
                _require_non_negative(
                    "VIBEMOUSE_RECORD_HOTKEY_CODE_2",
                    _read_int("VIBEMOUSE_RECORD_HOTKEY_CODE_2", 125),
                ),
                _require_non_negative(
                    "VIBEMOUSE_RECORD_HOTKEY_CODE_3",
                    _read_int("VIBEMOUSE_RECORD_HOTKEY_CODE_3", 193),
                ),
            }
        )
    )
    if len(record_hotkey_keycodes) != 3:
        raise ValueError("VIBEMOUSE_RECORD_HOTKEY_CODE_1/2/3 must be distinct")
    if front_button == rear_button:
        raise ValueError("VIBEMOUSE_FRONT_BUTTON and VIBEMOUSE_REAR_BUTTON must differ")
    button_debounce_ms = _require_non_negative(
        "VIBEMOUSE_BUTTON_DEBOUNCE_MS",
        _read_int("VIBEMOUSE_BUTTON_DEBOUNCE_MS", 150),
    )
    gestures_enabled = _read_bool("VIBEMOUSE_GESTURES_ENABLED", False)
    gesture_trigger_button = _read_choice(
        "VIBEMOUSE_GESTURE_TRIGGER_BUTTON",
        "rear",
        {"front", "rear", "right"},
    )
    gesture_threshold_px = _require_positive(
        "VIBEMOUSE_GESTURE_THRESHOLD_PX",
        _read_int("VIBEMOUSE_GESTURE_THRESHOLD_PX", 120),
    )
    gesture_freeze_pointer = _read_bool("VIBEMOUSE_GESTURE_FREEZE_POINTER", True)
    gesture_restore_cursor = _read_bool("VIBEMOUSE_GESTURE_RESTORE_CURSOR", True)
    gesture_actions = {
        "record_toggle",
        "send_enter",
        "workspace_left",
        "workspace_right",
        "noop",
    }
    gesture_up_action = _read_choice(
        "VIBEMOUSE_GESTURE_UP_ACTION",
        "record_toggle",
        gesture_actions,
    )
    gesture_down_action = _read_choice(
        "VIBEMOUSE_GESTURE_DOWN_ACTION",
        "noop",
        gesture_actions,
    )
    gesture_left_action = _read_choice(
        "VIBEMOUSE_GESTURE_LEFT_ACTION",
        "noop",
        gesture_actions,
    )
    gesture_right_action = _read_choice(
        "VIBEMOUSE_GESTURE_RIGHT_ACTION",
        "send_enter",
        gesture_actions,
    )
    enter_mode = _read_choice(
        "VIBEMOUSE_ENTER_MODE",
        "enter",
        {"enter", "ctrl_enter", "shift_enter", "none"},
    )
    openclaw_command = os.getenv("VIBEMOUSE_OPENCLAW_COMMAND", "openclaw").strip()
    if not openclaw_command:
        raise ValueError("VIBEMOUSE_OPENCLAW_COMMAND must not be empty")
    openclaw_agent_raw = os.getenv("VIBEMOUSE_OPENCLAW_AGENT", "main").strip()
    openclaw_agent = openclaw_agent_raw if openclaw_agent_raw else None
    openclaw_timeout_s = _require_positive_float(
        "VIBEMOUSE_OPENCLAW_TIMEOUT_S",
        _read_float("VIBEMOUSE_OPENCLAW_TIMEOUT_S", 20.0),
    )
    openclaw_retries = _require_non_negative(
        "VIBEMOUSE_OPENCLAW_RETRIES",
        _read_int("VIBEMOUSE_OPENCLAW_RETRIES", 0),
    )
    prewarm_delay_s = _require_non_negative_float(
        "VIBEMOUSE_PREWARM_DELAY_S",
        _read_float("VIBEMOUSE_PREWARM_DELAY_S", 0.0),
    )

    return AppConfig(
        sample_rate=sample_rate,
        channels=channels,
        dtype=os.getenv("VIBEMOUSE_DTYPE", "float32"),
        transcriber_backend=os.getenv("VIBEMOUSE_BACKEND", "funasr_onnx")
        .strip()
        .lower(),
        model_name=os.getenv("VIBEMOUSE_MODEL", "iic/SenseVoiceSmall"),
        log_level=_read_choice(
            "VIBEMOUSE_LOG_LEVEL",
            "info",
            {"debug", "info", "warning", "error", "critical"},
        ).upper(),
        device=os.getenv("VIBEMOUSE_DEVICE", "cpu"),
        language=os.getenv("VIBEMOUSE_LANGUAGE", "auto"),
        use_itn=_read_bool("VIBEMOUSE_USE_ITN", True),
        enable_vad=_read_bool("VIBEMOUSE_ENABLE_VAD", True),
        vad_max_single_segment_ms=vad_max_segment_ms,
        merge_vad=_read_bool("VIBEMOUSE_MERGE_VAD", True),
        merge_length_s=merge_length_s,
        fallback_to_cpu=_read_bool("VIBEMOUSE_FALLBACK_CPU", True),
        button_debounce_ms=button_debounce_ms,
        gestures_enabled=gestures_enabled,
        gesture_trigger_button=gesture_trigger_button,
        gesture_threshold_px=gesture_threshold_px,
        gesture_freeze_pointer=gesture_freeze_pointer,
        gesture_restore_cursor=gesture_restore_cursor,
        gesture_up_action=gesture_up_action,
        gesture_down_action=gesture_down_action,
        gesture_left_action=gesture_left_action,
        gesture_right_action=gesture_right_action,
        enter_mode=enter_mode,
        auto_paste=_read_bool("VIBEMOUSE_AUTO_PASTE", False),
        trust_remote_code=_read_bool("VIBEMOUSE_TRUST_REMOTE_CODE", False),
        prewarm_on_start=_read_bool("VIBEMOUSE_PREWARM_ON_START", True),
        prewarm_delay_s=prewarm_delay_s,
        status_file=status_file,
        openclaw_command=openclaw_command,
        openclaw_agent=openclaw_agent,
        openclaw_timeout_s=openclaw_timeout_s,
        openclaw_retries=openclaw_retries,
        front_button=front_button,
        rear_button=rear_button,
        record_hotkey_keycodes=record_hotkey_keycodes,
        temp_dir=temp_dir,
    )
