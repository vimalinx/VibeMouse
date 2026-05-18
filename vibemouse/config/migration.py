from __future__ import annotations

from collections.abc import Mapping

from vibemouse.config.schema import LATEST_CONFIG_SCHEMA_VERSION


_LEGACY_FIELD_PATHS: dict[str, tuple[str, str]] = {
    "sample_rate": ("transcriber", "sample_rate"),
    "channels": ("transcriber", "channels"),
    "dtype": ("transcriber", "dtype"),
    "backend": ("transcriber", "backend"),
    "transcriber_backend": ("transcriber", "backend"),
    "model": ("transcriber", "model_name"),
    "model_name": ("transcriber", "model_name"),
    "device": ("transcriber", "device"),
    "language": ("transcriber", "language"),
    "use_itn": ("transcriber", "use_itn"),
    "enable_vad": ("transcriber", "enable_vad"),
    "vad_max_single_segment_ms": ("transcriber", "vad_max_single_segment_ms"),
    "merge_vad": ("transcriber", "merge_vad"),
    "merge_length_s": ("transcriber", "merge_length_s"),
    "fallback_to_cpu": ("transcriber", "fallback_to_cpu"),
    "trust_remote_code": ("transcriber", "trust_remote_code"),
    "front_button": ("input", "front_button"),
    "rear_button": ("input", "rear_button"),
    "record_hotkey_keycodes": ("input", "record_hotkey_keycodes"),
    "recording_submit_keycode": ("input", "recording_submit_keycode"),
    "button_debounce_ms": ("input", "button_debounce_ms"),
    "gestures_enabled": ("input", "gestures_enabled"),
    "gesture_trigger_button": ("input", "gesture_trigger_button"),
    "gesture_threshold_px": ("input", "gesture_threshold_px"),
    "gesture_freeze_pointer": ("input", "gesture_freeze_pointer"),
    "gesture_restore_cursor": ("input", "gesture_restore_cursor"),
    "gesture_up_action": ("input", "gesture_up_action"),
    "gesture_down_action": ("input", "gesture_down_action"),
    "gesture_left_action": ("input", "gesture_left_action"),
    "gesture_right_action": ("input", "gesture_right_action"),
    "enter_mode": ("output", "enter_mode"),
    "auto_paste": ("output", "auto_paste"),
    "translation_toast_enabled": ("output", "translation_toast_enabled"),
    "readback_tts_enabled": ("output", "readback_tts_enabled"),
    "readback_tts_voice": ("output", "readback_tts_voice"),
    "translation_provider": ("translation", "provider"),
    "translation_deepl_auth_key": ("translation", "deepl_auth_key"),
    "translation_deepl_api_url": ("translation", "deepl_api_url"),
    "translation_libretranslate_url": ("translation", "libretranslate_url"),
    "translation_libretranslate_api_key": ("translation", "libretranslate_api_key"),
    "translation_mymemory_email": ("translation", "mymemory_email"),
    "translation_mymemory_key": ("translation", "mymemory_key"),
    "prewarm_on_start": ("startup", "prewarm_on_start"),
    "prewarm_delay_s": ("startup", "prewarm_delay_s"),
    "log_level": ("logs", "level"),
    "status_file": ("runtime", "status_file"),
    "temp_dir": ("runtime", "temp_dir"),
    "command_auth_token": ("runtime", "command_auth_token"),
}

_LEGACY_OPENCLAW_FLAT_FIELDS = {
    "openclaw_command",
    "openclaw_agent",
    "openclaw_timeout_s",
    "openclaw_retries",
}


def migrate_config_data(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise ValueError("config.json must contain a JSON object")

    document = {str(key): value for key, value in raw.items()}
    document = _coerce_legacy_flat_shape(document)
    document = _drop_legacy_openclaw_shape(document)

    schema_version = document.get("schema_version")
    if schema_version is None:
        document["schema_version"] = LATEST_CONFIG_SCHEMA_VERSION
        return document

    if schema_version != LATEST_CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported config schema_version: "
            + f"{schema_version}; expected {LATEST_CONFIG_SCHEMA_VERSION}"
        )
    return document


def _coerce_legacy_flat_shape(document: dict[str, object]) -> dict[str, object]:
    grouped: dict[str, object] = {}
    for key, value in document.items():
        if key == "schema_version":
            grouped[key] = value
            continue
        if key in _LEGACY_OPENCLAW_FLAT_FIELDS:
            continue
        if key in {
            "bindings",
            "transcriber",
            "input",
            "output",
            "translation",
            "startup",
            "logs",
            "runtime",
        }:
            grouped[key] = value
            continue

        target = _LEGACY_FIELD_PATHS.get(key)
        if target is None:
            grouped[key] = value
            continue

        section_name, field_name = target
        section = grouped.setdefault(section_name, {})
        if not isinstance(section, dict):
            raise ValueError(f"{section_name} must be an object")
        section.setdefault(field_name, value)

    return grouped


def _drop_legacy_openclaw_shape(document: dict[str, object]) -> dict[str, object]:
    migrated = dict(document)
    migrated.pop("openclaw", None)

    profiles = migrated.get("profiles")
    if isinstance(profiles, Mapping):
        cleaned_profiles = {str(key): value for key, value in profiles.items()}
        cleaned_profiles.pop("openclaw", None)
        migrated["profiles"] = cleaned_profiles

    dictionary = migrated.get("dictionary")
    if isinstance(dictionary, list):
        migrated_dictionary: list[object] = []
        for entry in dictionary:
            if not isinstance(entry, Mapping):
                migrated_dictionary.append(entry)
                continue
            cleaned_entry = {str(key): value for key, value in entry.items()}
            if str(cleaned_entry.get("scope", "")).strip().lower() == "openclaw":
                cleaned_entry["scope"] = "default"
            migrated_dictionary.append(cleaned_entry)
        migrated["dictionary"] = migrated_dictionary

    return migrated
