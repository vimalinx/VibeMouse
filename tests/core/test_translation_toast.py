from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from vibemouse.core.translation_toast import (
    _default_opus_mt_cache_dir,
    contains_chinese,
    maybe_show_translation_toast,
    translate_text_to_english,
)


class TranslationToastTests(unittest.TestCase):
    def test_contains_chinese_detects_cjk_text(self) -> None:
        self.assertTrue(contains_chinese("你好，world"))
        self.assertFalse(contains_chinese("hello world"))

    def test_translate_text_to_english_parses_google_payload(self) -> None:
        translated = translate_text_to_english(
            "你好，世界。",
            fetcher=lambda _text, _timeout: [
                [["Hello, world.", "你好，世界。", None, None, 1]]
            ],
        )

        self.assertEqual(translated, "Hello, world.")

    def test_translate_text_to_english_prefers_deepl_when_key_present(self) -> None:
        with patch(
            "vibemouse.core.translation_toast._post_json",
            return_value={"translations": [{"text": "Hello, world."}]},
        ) as post_json_mock:
            translated = translate_text_to_english(
                "你好，世界。",
                provider="auto",
                deepl_auth_key="test-key",
            )

        self.assertEqual(translated, "Hello, world.")
        self.assertIn("api-free.deepl.com", post_json_mock.call_args.args[0])

    def test_translate_text_to_english_falls_back_to_mymemory(self) -> None:
        with patch(
            "vibemouse.core.translation_toast.urlopen",
        ) as urlopen_mock:
            urlopen_mock.return_value.__enter__.return_value.read.return_value = (
                b'{"responseData":{"translatedText":"Hello world"}}'
            )
            translated = translate_text_to_english("你好世界", provider="auto")

        self.assertEqual(translated, "Hello world")

    def test_translate_text_to_english_passes_optional_mymemory_identity(self) -> None:
        with patch(
            "vibemouse.core.translation_toast.urlopen",
        ) as urlopen_mock:
            urlopen_mock.return_value.__enter__.return_value.read.return_value = (
                b'{"responseData":{"translatedText":"Hello world"}}'
            )
            translated = translate_text_to_english(
                "你好世界",
                provider="mymemory",
                mymemory_email="me@example.com",
                mymemory_key="abc123",
            )
            request = urlopen_mock.call_args.args[0]

        self.assertEqual(translated, "Hello world")
        self.assertIn("de=me%40example.com", request.full_url)
        self.assertIn("key=abc123", request.full_url)

    def test_translate_text_to_english_uses_libretranslate_when_selected(self) -> None:
        with patch(
            "vibemouse.core.translation_toast._post_json",
            return_value={"translatedText": "Hello"},
        ) as post_json_mock:
            translated = translate_text_to_english(
                "你好",
                provider="libretranslate",
                libretranslate_url="http://localhost:5000",
            )

        self.assertEqual(translated, "Hello")
        self.assertEqual(post_json_mock.call_args.args[0], "http://localhost:5000/translate")

    def test_translate_text_to_english_uses_opus_mt_when_selected(self) -> None:
        with patch(
            "vibemouse.core.translation_toast._translate_with_opus_mt",
            return_value="Hello from Opus-MT",
        ) as opus_mock:
            translated = translate_text_to_english(
                "你好",
                provider="opus_mt",
            )

        self.assertEqual(translated, "Hello from Opus-MT")
        opus_mock.assert_called_once_with("你好")

    def test_default_opus_mt_cache_dir_respects_env_override(self) -> None:
        with patch.dict(
            os.environ,
            {"VIBEMOUSE_OPUS_MT_CACHE_DIR": "/var/tmp/custom-opus-cache"},
            clear=False,
        ):
            cache_dir = _default_opus_mt_cache_dir()

        self.assertEqual(cache_dir, Path("/var/tmp/custom-opus-cache"))

    def test_translate_text_to_english_uses_opus_mt_when_selected(self) -> None:
        with patch(
            "vibemouse.core.translation_toast._OPUS_MT_TRANSLATOR.translate",
            return_value="Hello there",
        ) as translate_mock:
            translated = translate_text_to_english(
                "你好",
                provider="opus_mt",
            )

        self.assertEqual(translated, "Hello there")
        translate_mock.assert_called_once_with("你好")

    def test_maybe_show_translation_toast_skips_non_chinese_text(self) -> None:
        with patch(
            "vibemouse.core.translation_toast.show_system_notification",
        ) as notify_mock:
            shown = maybe_show_translation_toast("hello world")

        self.assertFalse(shown)
        notify_mock.assert_not_called()

    def test_maybe_show_translation_toast_notifies_with_english_translation(self) -> None:
        with (
            patch(
                "vibemouse.core.translation_toast.translate_text_to_english",
                return_value="Hello, world.",
            ) as translate_mock,
            patch(
                "vibemouse.core.translation_toast.show_system_notification",
                return_value=True,
            ) as notify_mock,
        ):
            shown = maybe_show_translation_toast("你好，世界。")

        self.assertTrue(shown)
        translate_mock.assert_called_once()
        notify_mock.assert_called_once_with(
            "English Translation",
            "Hello, world.",
            timeout_s=8.0,
        )

    def test_maybe_show_translation_toast_swallows_translation_failure(self) -> None:
        with (
            patch(
                "vibemouse.core.translation_toast.translate_text_to_english",
                side_effect=RuntimeError("network down"),
            ),
            self.assertLogs("vibemouse.core.translation_toast", level="WARNING") as captured,
        ):
            shown = maybe_show_translation_toast("你好，世界。")

        self.assertFalse(shown)
        self.assertTrue(
            any("Failed to translate transcript for toast" in entry for entry in captured.output)
        )
