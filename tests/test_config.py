from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from vibemouse.config import (
    build_default_config_document,
    config_document_to_app_config,
    load_config,
)


class LoadConfigTests(unittest.TestCase):
    def test_default_config_contains_profiles_and_dictionary(self) -> None:
        document = build_default_config_document()

        self.assertEqual(
            document["profiles"],
            {"default": "fast"},
        )
        self.assertEqual(document["dictionary"], [])

    def test_config_document_to_app_config_reads_profiles_and_dictionary(self) -> None:
        document = build_default_config_document()
        document["profiles"]["default"] = "enhanced"
        document["dictionary"] = [
            {
                "term": "Codex",
                "phrases": ["codex", "code x"],
                "weight": 8,
                "scope": "both",
                "enabled": True,
            }
        ]

        config = config_document_to_app_config(document)

        self.assertEqual(
            config.profiles,
            {"default": "enhanced"},
        )
        self.assertEqual(len(config.dictionary), 1)
        self.assertEqual(config.dictionary[0].term, "Codex")
        self.assertEqual(config.dictionary[0].phrases, ("codex", "code x"))
        self.assertEqual(config.dictionary[0].weight, 8)
        self.assertEqual(config.dictionary[0].scope, "both")
        self.assertTrue(config.dictionary[0].enabled)

    def test_defaults_disable_trust_remote_code(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()

        self.assertFalse(config.trust_remote_code)
        self.assertEqual(config.transcriber_backend, "funasr_onnx")
        self.assertFalse(config.auto_paste)
        self.assertFalse(config.gestures_enabled)
        self.assertEqual(config.gesture_trigger_button, "rear")
        self.assertEqual(config.gesture_threshold_px, 120)
        self.assertTrue(config.gesture_freeze_pointer)
        self.assertTrue(config.gesture_restore_cursor)
        self.assertEqual(config.gesture_up_action, "record_toggle")
        self.assertEqual(config.gesture_down_action, "noop")
        self.assertEqual(config.gesture_left_action, "noop")
        self.assertEqual(config.gesture_right_action, "send_enter")
        self.assertEqual(config.enter_mode, "enter")
        self.assertFalse(config.translation_toast_enabled)
        self.assertFalse(config.readback_tts_enabled)
        self.assertEqual(config.readback_tts_voice, "en-US-EmmaMultilingualNeural")
        self.assertEqual(config.translation_provider, "auto")
        self.assertIsNone(config.translation_deepl_auth_key)
        self.assertIsNone(config.translation_deepl_api_url)
        self.assertIsNone(config.translation_libretranslate_url)
        self.assertIsNone(config.translation_libretranslate_api_key)
        self.assertIsNone(config.translation_mymemory_email)
        self.assertIsNone(config.translation_mymemory_key)
        self.assertEqual(config.button_debounce_ms, 150)
        self.assertTrue(config.prewarm_on_start)
        self.assertEqual(config.prewarm_delay_s, 0.0)
        self.assertEqual(config.status_file.name, "vibemouse-status.json")
        self.assertIsNone(config.command_auth_token)
        self.assertEqual(config.front_button, "x1")
        self.assertEqual(config.rear_button, "x2")
        self.assertEqual(config.record_hotkey_keycodes, (42, 125, 193))
        self.assertIsNone(config.recording_submit_keycode)
        self.assertEqual(config.bindings, {})
        self.assertEqual(
            config.profiles,
            {"default": "fast"},
        )
        self.assertEqual(config.dictionary, ())

    def test_record_hotkey_keycodes_can_be_configured(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VIBEMOUSE_RECORD_HOTKEY_CODE_1": "58",
                "VIBEMOUSE_RECORD_HOTKEY_CODE_2": "125",
                "VIBEMOUSE_RECORD_HOTKEY_CODE_3": "193",
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.record_hotkey_keycodes, (58, 125, 193))

    def test_duplicate_record_hotkey_keycodes_are_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VIBEMOUSE_RECORD_HOTKEY_CODE_1": "42",
                "VIBEMOUSE_RECORD_HOTKEY_CODE_2": "42",
                "VIBEMOUSE_RECORD_HOTKEY_CODE_3": "193",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_RECORD_HOTKEY_CODE_1/2/3 must be distinct",
            ):
                _ = load_config()

    def test_recording_submit_keycode_can_be_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_RECORDING_SUBMIT_KEYCODE": "28"},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.recording_submit_keycode, 28)

    def test_blank_recording_submit_keycode_disables_listener(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_RECORDING_SUBMIT_KEYCODE": ""},
            clear=True,
        ):
            config = load_config()

        self.assertIsNone(config.recording_submit_keycode)

    def test_trust_remote_code_can_be_enabled(self) -> None:
        with patch.dict(
            os.environ, {"VIBEMOUSE_TRUST_REMOTE_CODE": "true"}, clear=True
        ):
            config = load_config()

        self.assertTrue(config.trust_remote_code)

    def test_backend_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_BACKEND": "funasr"}, clear=True):
            config = load_config()

        self.assertEqual(config.transcriber_backend, "funasr")

    def test_auto_paste_can_be_enabled(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_AUTO_PASTE": "true"}, clear=True):
            config = load_config()

        self.assertTrue(config.auto_paste)

    def test_translation_settings_can_be_configured_via_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VIBEMOUSE_TRANSLATION_TOAST_ENABLED": "false",
                "VIBEMOUSE_READBACK_TTS_ENABLED": "true",
                "VIBEMOUSE_READBACK_TTS_VOICE": "en-US-EmmaMultilingualNeural",
                "VIBEMOUSE_TRANSLATION_PROVIDER": "deepl",
                "VIBEMOUSE_DEEPL_AUTH_KEY": "secret",
                "VIBEMOUSE_DEEPL_API_URL": "https://api-free.deepl.com/v2/translate",
                "VIBEMOUSE_LIBRETRANSLATE_URL": "http://127.0.0.1:5000",
                "VIBEMOUSE_LIBRETRANSLATE_API_KEY": "libre-key",
                "VIBEMOUSE_MYMEMORY_EMAIL": "me@example.com",
                "VIBEMOUSE_MYMEMORY_KEY": "memory-key",
            },
            clear=True,
        ):
            config = load_config()

        self.assertFalse(config.translation_toast_enabled)
        self.assertTrue(config.readback_tts_enabled)
        self.assertEqual(config.readback_tts_voice, "en-US-EmmaMultilingualNeural")
        self.assertEqual(config.translation_provider, "deepl")
        self.assertEqual(config.translation_deepl_auth_key, "secret")
        self.assertEqual(
            config.translation_deepl_api_url,
            "https://api-free.deepl.com/v2/translate",
        )
        self.assertEqual(config.translation_libretranslate_url, "http://127.0.0.1:5000")
        self.assertEqual(config.translation_libretranslate_api_key, "libre-key")
        self.assertEqual(config.translation_mymemory_email, "me@example.com")
        self.assertEqual(config.translation_mymemory_key, "memory-key")

    def test_translation_provider_can_be_set_to_opus_mt(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_TRANSLATION_PROVIDER": "opus_mt"},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.translation_provider, "opus_mt")

    def test_gestures_can_be_enabled(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_GESTURES_ENABLED": "true"}, clear=True):
            config = load_config()

        self.assertTrue(config.gestures_enabled)

    def test_gesture_freeze_pointer_can_be_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_GESTURE_FREEZE_POINTER": "false"},
            clear=True,
        ):
            config = load_config()

        self.assertFalse(config.gesture_freeze_pointer)

    def test_gesture_restore_cursor_can_be_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_GESTURE_RESTORE_CURSOR": "false"},
            clear=True,
        ):
            config = load_config()

        self.assertFalse(config.gesture_restore_cursor)

    def test_prewarm_on_start_can_be_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_PREWARM_ON_START": "false"},
            clear=True,
        ):
            config = load_config()

        self.assertFalse(config.prewarm_on_start)

    def test_prewarm_delay_can_be_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_PREWARM_DELAY_S": "2.5"},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.prewarm_delay_s, 2.5)

    def test_negative_prewarm_delay_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_PREWARM_DELAY_S": "-0.1"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_PREWARM_DELAY_S must be a non-negative float",
            ):
                _ = load_config()

    def test_status_file_can_be_overridden(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_STATUS_FILE": "/tmp/custom-vibemouse-status.json"},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(
            config.status_file.as_posix(),
            "/tmp/custom-vibemouse-status.json",
        )

    def test_enter_mode_can_be_configured(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_ENTER_MODE": "ctrl_enter"}, clear=True):
            config = load_config()

        self.assertEqual(config.enter_mode, "ctrl_enter")

    def test_enter_mode_supports_none(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_ENTER_MODE": "none"}, clear=True):
            config = load_config()

        self.assertEqual(config.enter_mode, "none")

    def test_invalid_enter_mode_is_rejected(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_ENTER_MODE": "meta_enter"}, clear=True):
            with self.assertRaisesRegex(
                ValueError, "VIBEMOUSE_ENTER_MODE must be one of"
            ):
                _ = load_config()

    def test_invalid_gesture_trigger_button_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_GESTURE_TRIGGER_BUTTON": "middle"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_GESTURE_TRIGGER_BUTTON must be one of",
            ):
                _ = load_config()

    def test_gesture_trigger_button_supports_right(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_GESTURE_TRIGGER_BUTTON": "right"},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.gesture_trigger_button, "right")

    def test_gesture_action_supports_workspace_switches(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VIBEMOUSE_GESTURE_LEFT_ACTION": "workspace_left",
                "VIBEMOUSE_GESTURE_RIGHT_ACTION": "workspace_right",
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.gesture_left_action, "workspace_left")
        self.assertEqual(config.gesture_right_action, "workspace_right")

    def test_invalid_gesture_action_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_GESTURE_UP_ACTION": "paste_now"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_GESTURE_UP_ACTION must be one of",
            ):
                _ = load_config()

    def test_negative_debounce_is_rejected(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_BUTTON_DEBOUNCE_MS": "-1"}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_BUTTON_DEBOUNCE_MS must be a non-negative integer",
            ):
                _ = load_config()

    def test_invalid_integer_reports_variable_name(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_SAMPLE_RATE": "abc"}, clear=True):
            with self.assertRaisesRegex(
                ValueError, "VIBEMOUSE_SAMPLE_RATE must be an integer"
            ):
                _ = load_config()

    def test_non_positive_integer_is_rejected(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_MERGE_LENGTH_S": "0"}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_MERGE_LENGTH_S must be a positive integer",
            ):
                _ = load_config()

    def test_non_positive_gesture_threshold_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_GESTURE_THRESHOLD_PX": "0"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_GESTURE_THRESHOLD_PX must be a positive integer",
            ):
                _ = load_config()

    def test_invalid_button_value_is_rejected(self) -> None:
        with patch.dict(os.environ, {"VIBEMOUSE_FRONT_BUTTON": "x3"}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_FRONT_BUTTON must be either 'x1' or 'x2'",
            ):
                _ = load_config()

    def test_command_auth_token_can_be_configured(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_COMMAND_AUTH_TOKEN": "  reload-secret  "},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.command_auth_token, "reload-secret")

    def test_same_front_and_rear_buttons_are_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {
                "VIBEMOUSE_FRONT_BUTTON": "x1",
                "VIBEMOUSE_REAR_BUTTON": "x1",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "VIBEMOUSE_FRONT_BUTTON and VIBEMOUSE_REAR_BUTTON must differ",
            ):
                _ = load_config()
