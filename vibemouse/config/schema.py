from __future__ import annotations

import copy
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from vibemouse.core.commands import KNOWN_COMMAND_NAMES, is_valid_event_name


LATEST_CONFIG_SCHEMA_VERSION = 1

_BUTTON_CHOICES = {"x1", "x2"}
_GESTURE_TRIGGER_CHOICES = {"front", "rear", "right"}
_GESTURE_ACTION_CHOICES = {
    "record_toggle",
    "send_enter",
    "workspace_left",
    "workspace_right",
    "noop",
}
_ENTER_MODE_CHOICES = {"enter", "ctrl_enter", "shift_enter", "none"}
_LOG_LEVEL_CHOICES = {"debug", "info", "warning", "error", "critical"}
_STATUS_STATE_CHOICES = {"idle", "recording", "processing"}
_LISTENER_MODE_CHOICES = {"inline", "child", "off"}
_PROFILE_TARGET_CHOICES = {"default"}
_PROFILE_MODE_CHOICES = {"fast", "enhanced"}
_DICTIONARY_SCOPE_CHOICES = {"default", "both"}
_TRANSLATION_PROVIDER_CHOICES = {
    "auto",
    "deepl",
    "opus_mt",
    "libretranslate",
    "mymemory",
}
_DICTIONARY_WEIGHT_MIN = 1
_DICTIONARY_WEIGHT_MAX = 10


@dataclass(frozen=True)
class DictionaryEntry:
    term: str
    phrases: tuple[str, ...]
    weight: int
    scope: str
    enabled: bool


@dataclass(frozen=True)
class AppConfig:
    bindings: dict[str, str]
    profiles: dict[str, str]
    dictionary: tuple[DictionaryEntry, ...]
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
    translation_toast_enabled: bool
    readback_tts_enabled: bool
    readback_tts_voice: str
    translation_provider: str
    translation_deepl_auth_key: str | None
    translation_deepl_api_url: str | None
    translation_libretranslate_url: str | None
    translation_libretranslate_api_key: str | None
    translation_mymemory_email: str | None
    translation_mymemory_key: str | None
    trust_remote_code: bool
    prewarm_on_start: bool
    prewarm_delay_s: float
    status_file: Path
    command_auth_token: str | None
    front_button: str
    rear_button: str
    record_hotkey_keycodes: tuple[int, ...]
    recording_submit_keycode: int | None
    temp_dir: Path


def default_config_path() -> Path:
    home_dir = _safe_home_dir()
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if appdata:
            base_dir = Path(appdata)
        else:
            base_dir = home_dir / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base_dir = home_dir / "Library" / "Application Support"
    else:
        base_dir = Path(os.getenv("XDG_CONFIG_HOME", str(home_dir / ".config")))
    return base_dir / "vibemouse" / "config.json"


def default_temp_dir() -> Path:
    return Path(tempfile.gettempdir()) / "vibemouse"


def default_status_file() -> Path:
    runtime_dir = Path(os.getenv("XDG_RUNTIME_DIR", tempfile.gettempdir()))
    return runtime_dir / "vibemouse-status.json"


def build_default_config_document() -> dict[str, object]:
    return {
        "schema_version": LATEST_CONFIG_SCHEMA_VERSION,
        "bindings": {},
        "profiles": {
            "default": "fast",
        },
        "dictionary": [],
        "transcriber": {
            "sample_rate": 16000,
            "channels": 1,
            "dtype": "float32",
            "backend": "funasr_onnx",
            "model_name": "iic/SenseVoiceSmall",
            "device": "cpu",
            "language": "auto",
            "use_itn": True,
            "enable_vad": True,
            "vad_max_single_segment_ms": 30000,
            "merge_vad": True,
            "merge_length_s": 15,
            "fallback_to_cpu": True,
            "trust_remote_code": False,
        },
        "input": {
            "front_button": "x1",
            "rear_button": "x2",
            "record_hotkey_keycodes": [42, 125, 193],
            "recording_submit_keycode": None,
            "button_debounce_ms": 150,
            "gestures_enabled": False,
            "gesture_trigger_button": "rear",
            "gesture_threshold_px": 120,
            "gesture_freeze_pointer": True,
            "gesture_restore_cursor": True,
            "gesture_up_action": "record_toggle",
            "gesture_down_action": "noop",
            "gesture_left_action": "noop",
            "gesture_right_action": "send_enter",
        },
        "output": {
            "enter_mode": "enter",
            "auto_paste": False,
            "translation_toast_enabled": False,
            "readback_tts_enabled": False,
            "readback_tts_voice": "en-US-EmmaMultilingualNeural",
        },
        "translation": {
            "provider": "auto",
            "deepl_auth_key": None,
            "deepl_api_url": None,
            "libretranslate_url": None,
            "libretranslate_api_key": None,
            "mymemory_email": None,
            "mymemory_key": None,
        },
        "startup": {
            "prewarm_on_start": True,
            "prewarm_delay_s": 0.0,
        },
        "logs": {
            "level": "info",
        },
        "runtime": {
            "status_file": str(default_status_file()),
            "temp_dir": str(default_temp_dir()),
            "command_auth_token": None,
        },
    }


def config_document_to_app_config(document: Mapping[str, object]) -> AppConfig:
    normalized = normalize_config_document(document)
    bindings = _expect_mapping(normalized, "bindings")
    profiles = _expect_mapping(normalized, "profiles")
    transcriber = _expect_mapping(normalized, "transcriber")
    input_section = _expect_mapping(normalized, "input")
    output = _expect_mapping(normalized, "output")
    translation = _expect_mapping(normalized, "translation")
    startup = _expect_mapping(normalized, "startup")
    logs = _expect_mapping(normalized, "logs")
    runtime = _expect_mapping(normalized, "runtime")

    return AppConfig(
        bindings={str(key): str(value) for key, value in bindings.items()},
        profiles={str(key): str(value) for key, value in profiles.items()},
        dictionary=tuple(
            DictionaryEntry(
                term=str(entry["term"]),
                phrases=tuple(str(phrase) for phrase in _expect_list(entry, "phrases")),
                weight=int(entry["weight"]),
                scope=str(entry["scope"]),
                enabled=bool(entry["enabled"]),
            )
            for entry in _expect_mapping_list(normalized, "dictionary")
        ),
        sample_rate=int(transcriber["sample_rate"]),
        channels=int(transcriber["channels"]),
        dtype=str(transcriber["dtype"]),
        transcriber_backend=str(transcriber["backend"]),
        model_name=str(transcriber["model_name"]),
        log_level=str(logs["level"]).upper(),
        device=str(transcriber["device"]),
        language=str(transcriber["language"]),
        use_itn=bool(transcriber["use_itn"]),
        enable_vad=bool(transcriber["enable_vad"]),
        vad_max_single_segment_ms=int(transcriber["vad_max_single_segment_ms"]),
        merge_vad=bool(transcriber["merge_vad"]),
        merge_length_s=int(transcriber["merge_length_s"]),
        fallback_to_cpu=bool(transcriber["fallback_to_cpu"]),
        button_debounce_ms=int(input_section["button_debounce_ms"]),
        gestures_enabled=bool(input_section["gestures_enabled"]),
        gesture_trigger_button=str(input_section["gesture_trigger_button"]),
        gesture_threshold_px=int(input_section["gesture_threshold_px"]),
        gesture_freeze_pointer=bool(input_section["gesture_freeze_pointer"]),
        gesture_restore_cursor=bool(input_section["gesture_restore_cursor"]),
        gesture_up_action=str(input_section["gesture_up_action"]),
        gesture_down_action=str(input_section["gesture_down_action"]),
        gesture_left_action=str(input_section["gesture_left_action"]),
        gesture_right_action=str(input_section["gesture_right_action"]),
        enter_mode=str(output["enter_mode"]),
        auto_paste=bool(output["auto_paste"]),
        translation_toast_enabled=bool(output["translation_toast_enabled"]),
        readback_tts_enabled=bool(output["readback_tts_enabled"]),
        readback_tts_voice=str(output["readback_tts_voice"]),
        translation_provider=str(translation["provider"]),
        translation_deepl_auth_key=_coerce_optional_string(
            translation["deepl_auth_key"]
        ),
        translation_deepl_api_url=_coerce_optional_string(
            translation["deepl_api_url"]
        ),
        translation_libretranslate_url=_coerce_optional_string(
            translation["libretranslate_url"]
        ),
        translation_libretranslate_api_key=_coerce_optional_string(
            translation["libretranslate_api_key"]
        ),
        translation_mymemory_email=_coerce_optional_string(
            translation["mymemory_email"]
        ),
        translation_mymemory_key=_coerce_optional_string(
            translation["mymemory_key"]
        ),
        trust_remote_code=bool(transcriber["trust_remote_code"]),
        prewarm_on_start=bool(startup["prewarm_on_start"]),
        prewarm_delay_s=float(startup["prewarm_delay_s"]),
        status_file=Path(str(runtime["status_file"])),
        command_auth_token=_coerce_optional_string(runtime["command_auth_token"]),
        front_button=str(input_section["front_button"]),
        rear_button=str(input_section["rear_button"]),
        record_hotkey_keycodes=tuple(
            int(value)
            for value in _expect_list(input_section, "record_hotkey_keycodes")
        ),
        recording_submit_keycode=_coerce_optional_int(
            input_section["recording_submit_keycode"],
            "input.recording_submit_keycode",
        ),
        temp_dir=Path(str(runtime["temp_dir"])),
    )


def normalize_config_document(document: Mapping[str, object]) -> dict[str, object]:
    defaults = build_default_config_document()
    allowed_top_level = {
        "schema_version",
        "bindings",
        "profiles",
        "dictionary",
        "transcriber",
        "input",
        "output",
        "translation",
        "startup",
        "logs",
        "runtime",
    }
    unknown_top_level = set(document.keys()) - allowed_top_level
    if unknown_top_level:
        names = ", ".join(sorted(unknown_top_level))
        raise ValueError(f"Unknown config section(s): {names}")

    schema_version = _coerce_non_negative_int(
        document.get("schema_version", LATEST_CONFIG_SCHEMA_VERSION),
        "schema_version",
    )
    if schema_version != LATEST_CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported config schema_version: "
            + f"{schema_version}; expected {LATEST_CONFIG_SCHEMA_VERSION}"
        )

    normalized: dict[str, object] = copy.deepcopy(defaults)
    normalized["schema_version"] = schema_version
    normalized["bindings"] = _normalize_bindings(document.get("bindings", {}))
    normalized["profiles"] = _normalize_profiles_section(
        _merge_section(defaults, document, "profiles")
    )
    normalized["dictionary"] = _normalize_dictionary_entries(
        document.get("dictionary", defaults["dictionary"])
    )
    normalized["transcriber"] = _normalize_transcriber_section(
        _merge_section(defaults, document, "transcriber")
    )
    normalized["input"] = _normalize_input_section(
        _merge_section(defaults, document, "input")
    )
    normalized["output"] = _normalize_output_section(
        _merge_section(defaults, document, "output")
    )
    normalized["translation"] = _normalize_translation_section(
        _merge_section(defaults, document, "translation")
    )
    normalized["startup"] = _normalize_startup_section(
        _merge_section(defaults, document, "startup")
    )
    normalized["logs"] = _normalize_logs_section(
        _merge_section(defaults, document, "logs")
    )
    normalized["runtime"] = _normalize_runtime_section(
        _merge_section(defaults, document, "runtime")
    )
    return normalized


def normalize_status_document(payload: Mapping[str, object]) -> dict[str, object]:
    allowed_keys = {
        "recording",
        "state",
        "listener_mode",
        "last_transcript",
        "ipc_socket",
        "ipc_port",
        "updated_at",
    }
    unknown_keys = set(payload.keys()) - allowed_keys
    if unknown_keys:
        names = ", ".join(sorted(unknown_keys))
        raise ValueError(f"Unknown status field(s): {names}")

    recording = payload.get("recording")
    if not isinstance(recording, bool):
        raise ValueError("status.recording must be a boolean")

    state = _coerce_choice(payload.get("state"), "status.state", _STATUS_STATE_CHOICES)
    normalized: dict[str, object] = {
        "recording": recording,
        "state": state,
    }

    listener_mode = payload.get("listener_mode")
    if listener_mode is not None:
        normalized["listener_mode"] = _coerce_choice(
            listener_mode,
            "status.listener_mode",
            _LISTENER_MODE_CHOICES,
        )

    last_transcript = payload.get("last_transcript")
    if last_transcript is not None:
        normalized["last_transcript"] = _coerce_string(
            last_transcript,
            "status.last_transcript",
        )

    ipc_socket = payload.get("ipc_socket")
    if ipc_socket is not None:
        normalized["ipc_socket"] = _coerce_string(ipc_socket, "status.ipc_socket")

    ipc_port = payload.get("ipc_port")
    if ipc_port is not None:
        normalized["ipc_port"] = _coerce_positive_int(ipc_port, "status.ipc_port")

    updated_at = payload.get("updated_at")
    if updated_at is not None:
        normalized["updated_at"] = _coerce_string(updated_at, "status.updated_at")

    return normalized


def _merge_section(
    defaults: Mapping[str, object],
    document: Mapping[str, object],
    section_name: str,
) -> dict[str, object]:
    default_section = _expect_mapping(defaults, section_name)
    raw_section = document.get(section_name, {})
    if raw_section is None:
        raw_section = {}
    section = _expect_mapping_value(raw_section, section_name)
    unknown_keys = set(section.keys()) - set(default_section.keys())
    if unknown_keys:
        names = ", ".join(sorted(unknown_keys))
        raise ValueError(f"Unknown {section_name} field(s): {names}")

    merged = copy.deepcopy(default_section)
    merged.update(section)
    return merged


def _normalize_bindings(raw: object) -> dict[str, str]:
    section = _expect_mapping_value(raw, "bindings")
    normalized: dict[str, str] = {}
    for key, value in section.items():
        event_name = _coerce_non_empty_string(key, "bindings key").lower()
        if not is_valid_event_name(event_name):
            raise ValueError(
                "bindings key must use normalized event segments separated by dots; "
                + f"got {event_name!r}"
            )
        command_name = _coerce_non_empty_string(
            value,
            f"bindings[{event_name!r}]",
        ).lower()
        if command_name not in KNOWN_COMMAND_NAMES:
            options = ", ".join(sorted(KNOWN_COMMAND_NAMES))
            raise ValueError(
                f"bindings[{event_name!r}] must be one of: {options}; got {command_name!r}"
            )
        normalized[event_name] = command_name
    return normalized


def _normalize_transcriber_section(section: Mapping[str, object]) -> dict[str, object]:
    backend = _coerce_non_empty_string(section["backend"], "transcriber.backend").lower()
    model_name = _coerce_non_empty_string(
        section["model_name"], "transcriber.model_name"
    )
    device = _coerce_non_empty_string(section["device"], "transcriber.device")
    language = _coerce_non_empty_string(
        section["language"], "transcriber.language"
    )
    dtype = _coerce_non_empty_string(section["dtype"], "transcriber.dtype")
    return {
        "sample_rate": _coerce_positive_int(
            section["sample_rate"], "transcriber.sample_rate"
        ),
        "channels": _coerce_positive_int(section["channels"], "transcriber.channels"),
        "dtype": dtype,
        "backend": backend,
        "model_name": model_name,
        "device": device,
        "language": language,
        "use_itn": _coerce_bool(section["use_itn"], "transcriber.use_itn"),
        "enable_vad": _coerce_bool(
            section["enable_vad"], "transcriber.enable_vad"
        ),
        "vad_max_single_segment_ms": _coerce_positive_int(
            section["vad_max_single_segment_ms"],
            "transcriber.vad_max_single_segment_ms",
        ),
        "merge_vad": _coerce_bool(section["merge_vad"], "transcriber.merge_vad"),
        "merge_length_s": _coerce_positive_int(
            section["merge_length_s"], "transcriber.merge_length_s"
        ),
        "fallback_to_cpu": _coerce_bool(
            section["fallback_to_cpu"], "transcriber.fallback_to_cpu"
        ),
        "trust_remote_code": _coerce_bool(
            section["trust_remote_code"], "transcriber.trust_remote_code"
        ),
    }


def _normalize_profiles_section(section: Mapping[str, object]) -> dict[str, object]:
    expected_targets = set(section.keys())
    if expected_targets != _PROFILE_TARGET_CHOICES:
        missing = _PROFILE_TARGET_CHOICES - expected_targets
        unknown = expected_targets - _PROFILE_TARGET_CHOICES
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown {', '.join(sorted(unknown))}")
        raise ValueError("profiles must define default target" + (
            f" ({'; '.join(details)})" if details else ""
        ))

    return {
        target: _coerce_choice(
            section[target],
            f"profiles.{target}",
            _PROFILE_MODE_CHOICES,
        )
        for target in sorted(_PROFILE_TARGET_CHOICES)
    }


def _normalize_dictionary_entries(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list | tuple):
        raise ValueError("dictionary must be a list")

    normalized: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        item = _expect_mapping_value(entry, f"dictionary[{index}]")
        unknown_keys = set(item.keys()) - {"term", "phrases", "weight", "scope", "enabled"}
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise ValueError(f"Unknown dictionary[{index}] field(s): {names}")

        phrases_raw = item.get("phrases")
        if not isinstance(phrases_raw, list):
            raise ValueError(f"dictionary[{index}].phrases must be a list")

        phrases = [
            _coerce_non_empty_string(phrase, f"dictionary[{index}].phrases[{phrase_index}]")
            for phrase_index, phrase in enumerate(phrases_raw)
        ]
        if not phrases:
            raise ValueError(f"dictionary[{index}].phrases must contain at least one value")

        normalized.append(
            {
                "term": _coerce_non_empty_string(item.get("term"), f"dictionary[{index}].term"),
                "phrases": phrases,
                "weight": _coerce_bounded_int(
                    item.get("weight"),
                    f"dictionary[{index}].weight",
                    minimum=_DICTIONARY_WEIGHT_MIN,
                    maximum=_DICTIONARY_WEIGHT_MAX,
                ),
                "scope": _coerce_choice(
                    item.get("scope"),
                    f"dictionary[{index}].scope",
                    _DICTIONARY_SCOPE_CHOICES,
                ),
                "enabled": _coerce_bool(item.get("enabled"), f"dictionary[{index}].enabled"),
            }
        )

    return normalized


def _normalize_input_section(section: Mapping[str, object]) -> dict[str, object]:
    front_button = _coerce_choice(
        section["front_button"], "input.front_button", _BUTTON_CHOICES
    )
    rear_button = _coerce_choice(
        section["rear_button"], "input.rear_button", _BUTTON_CHOICES
    )
    if front_button == rear_button:
        raise ValueError("input.front_button and input.rear_button must differ")

    return {
        "front_button": front_button,
        "rear_button": rear_button,
        "record_hotkey_keycodes": _normalize_record_hotkey_keycodes(
            section["record_hotkey_keycodes"]
        ),
        "recording_submit_keycode": _coerce_optional_int(
            section["recording_submit_keycode"],
            "input.recording_submit_keycode",
        ),
        "button_debounce_ms": _coerce_non_negative_int(
            section["button_debounce_ms"],
            "input.button_debounce_ms",
        ),
        "gestures_enabled": _coerce_bool(
            section["gestures_enabled"], "input.gestures_enabled"
        ),
        "gesture_trigger_button": _coerce_choice(
            section["gesture_trigger_button"],
            "input.gesture_trigger_button",
            _GESTURE_TRIGGER_CHOICES,
        ),
        "gesture_threshold_px": _coerce_positive_int(
            section["gesture_threshold_px"],
            "input.gesture_threshold_px",
        ),
        "gesture_freeze_pointer": _coerce_bool(
            section["gesture_freeze_pointer"],
            "input.gesture_freeze_pointer",
        ),
        "gesture_restore_cursor": _coerce_bool(
            section["gesture_restore_cursor"],
            "input.gesture_restore_cursor",
        ),
        "gesture_up_action": _coerce_choice(
            section["gesture_up_action"],
            "input.gesture_up_action",
            _GESTURE_ACTION_CHOICES,
        ),
        "gesture_down_action": _coerce_choice(
            section["gesture_down_action"],
            "input.gesture_down_action",
            _GESTURE_ACTION_CHOICES,
        ),
        "gesture_left_action": _coerce_choice(
            section["gesture_left_action"],
            "input.gesture_left_action",
            _GESTURE_ACTION_CHOICES,
        ),
        "gesture_right_action": _coerce_choice(
            section["gesture_right_action"],
            "input.gesture_right_action",
            _GESTURE_ACTION_CHOICES,
        ),
    }


def _normalize_output_section(section: Mapping[str, object]) -> dict[str, object]:
    return {
        "enter_mode": _coerce_choice(
            section["enter_mode"], "output.enter_mode", _ENTER_MODE_CHOICES
        ),
        "auto_paste": _coerce_bool(section["auto_paste"], "output.auto_paste"),
        "translation_toast_enabled": _coerce_bool(
            section["translation_toast_enabled"],
            "output.translation_toast_enabled",
        ),
        "readback_tts_enabled": _coerce_bool(
            section["readback_tts_enabled"],
            "output.readback_tts_enabled",
        ),
        "readback_tts_voice": _coerce_non_empty_string(
            section["readback_tts_voice"],
            "output.readback_tts_voice",
        ),
    }


def _normalize_translation_section(section: Mapping[str, object]) -> dict[str, object]:
    return {
        "provider": _coerce_choice(
            section["provider"],
            "translation.provider",
            _TRANSLATION_PROVIDER_CHOICES,
        ),
        "deepl_auth_key": _coerce_optional_string(section["deepl_auth_key"]),
        "deepl_api_url": _coerce_optional_string(section["deepl_api_url"]),
        "libretranslate_url": _coerce_optional_string(section["libretranslate_url"]),
        "libretranslate_api_key": _coerce_optional_string(
            section["libretranslate_api_key"]
        ),
        "mymemory_email": _coerce_optional_string(section["mymemory_email"]),
        "mymemory_key": _coerce_optional_string(section["mymemory_key"]),
    }


def _normalize_startup_section(section: Mapping[str, object]) -> dict[str, object]:
    return {
        "prewarm_on_start": _coerce_bool(
            section["prewarm_on_start"], "startup.prewarm_on_start"
        ),
        "prewarm_delay_s": _coerce_non_negative_float(
            section["prewarm_delay_s"], "startup.prewarm_delay_s"
        ),
    }


def _normalize_logs_section(section: Mapping[str, object]) -> dict[str, object]:
    return {
        "level": _coerce_choice(section["level"], "logs.level", _LOG_LEVEL_CHOICES),
    }


def _normalize_runtime_section(section: Mapping[str, object]) -> dict[str, object]:
    return {
        "status_file": str(_coerce_path(section["status_file"], "runtime.status_file")),
        "temp_dir": str(_coerce_path(section["temp_dir"], "runtime.temp_dir")),
        "command_auth_token": _coerce_optional_string(section["command_auth_token"]),
    }


def _normalize_record_hotkey_keycodes(raw: object) -> list[int]:
    if not isinstance(raw, list | tuple):
        raise ValueError("input.record_hotkey_keycodes must be a list of three integers")
    values = [
        _coerce_non_negative_int(
            value,
            f"input.record_hotkey_keycodes[{index}]",
        )
        for index, value in enumerate(raw)
    ]
    if len(values) != 3:
        raise ValueError("input.record_hotkey_keycodes must contain exactly three values")
    if len(set(values)) != 3:
        raise ValueError("input.record_hotkey_keycodes must contain distinct values")
    return values


def _expect_mapping(source: Mapping[str, object], key: str) -> dict[str, object]:
    return _expect_mapping_value(source.get(key), key)


def _expect_mapping_value(raw: object, name: str) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{name} must be an object")
    return {str(key): value for key, value in raw.items()}


def _expect_list(source: Mapping[str, object], key: str) -> list[object]:
    raw = source.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list")
    return raw


def _expect_mapping_list(source: Mapping[str, object], key: str) -> list[dict[str, object]]:
    raw = source.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list")
    return [
        _expect_mapping_value(value, f"{key}[{index}]")
        for index, value in enumerate(raw)
    ]


def _coerce_bool(raw: object, name: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"{name} must be a boolean")
    return raw


def _coerce_positive_int(raw: object, name: str) -> int:
    value = _coerce_non_negative_int(raw, name)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _coerce_non_negative_int(raw: object, name: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{name} must be an integer")
    if raw < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return raw


def _coerce_bounded_int(
    raw: object,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _coerce_non_negative_int(raw, name)
    if value < minimum or value > maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _coerce_positive_float(raw: object, name: str) -> float:
    value = _coerce_non_negative_float(raw, name)
    if value <= 0:
        raise ValueError(f"{name} must be a positive float")
    return value


def _coerce_non_negative_float(raw: object, name: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{name} must be a float")
    value = float(raw)
    if value < 0:
        raise ValueError(f"{name} must be a non-negative float")
    return value


def _coerce_choice(raw: object, name: str, allowed: set[str]) -> str:
    value = _coerce_non_empty_string(raw, name).lower()
    if value not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {options}; got {value!r}")
    return value


def _coerce_string(raw: object, name: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{name} must be a string")
    return raw


def _coerce_non_empty_string(raw: object, name: str) -> str:
    value = _coerce_string(raw, name).strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _coerce_optional_string(raw: object) -> str | None:
    if raw is None:
        return None
    value = _coerce_string(raw, "optional string").strip()
    return value or None


def _coerce_optional_int(raw: object, name: str) -> int | None:
    if raw is None:
        return None
    return _coerce_non_negative_int(raw, name)


def _coerce_path(raw: object, name: str) -> Path:
    if isinstance(raw, Path):
        return raw
    return Path(_coerce_string(raw, name))


def _safe_home_dir() -> Path:
    try:
        return Path.home()
    except RuntimeError:
        return Path(tempfile.gettempdir()) / "vibemouse-home"
