from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

from vibemouse.config import (
    AppConfig,
    build_default_config_document,
    config_document_to_app_config,
)
from vibemouse.core.backends.funasr_enhanced import FunASREnhancedBackend


def _build_config() -> AppConfig:
    document = build_default_config_document()
    document["profiles"] = {"default": "enhanced"}
    return config_document_to_app_config(document)


class _FakeModel:
    def __init__(self, text: str) -> None:
        self._text = text
        self.generate_kwargs: dict[str, object] = {}

    def generate(self, **kwargs: object) -> list[dict[str, object]]:
        self.generate_kwargs = kwargs
        return [{"text": self._text}]


class _FakeAutoModel:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)

    def generate(self, **kwargs: object) -> list[dict[str, object]]:
        return [{"text": "你好，世界。"}]


class FunASREnhancedBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeAutoModel.calls = []

    def test_prewarm_initializes_asr_with_punctuation_model(self) -> None:
        subject = FunASREnhancedBackend(_build_config())

        with patch.object(subject, "_load_automodel_ctor", return_value=_FakeAutoModel):
            subject.prewarm()

        self.assertEqual(
            _FakeAutoModel.calls,
            [
                {
                    "model": "paraformer-zh",
                    "punc_model": "ct-punc",
                    "device": "cpu",
                    "disable_update": True,
                    "disable_pbar": True,
                    "vad_model": "fsmn-vad",
                    "vad_kwargs": {"max_single_segment_time": 30000},
                    "merge_length_s": 15,
                }
            ],
        )

    def test_prewarm_omits_vad_when_disabled(self) -> None:
        config = replace(_build_config(), enable_vad=False)
        subject = FunASREnhancedBackend(config)

        with patch.object(subject, "_load_automodel_ctor", return_value=_FakeAutoModel):
            subject.prewarm()

        self.assertEqual(
            _FakeAutoModel.calls,
            [
                {
                    "model": "paraformer-zh",
                    "punc_model": "ct-punc",
                    "device": "cpu",
                    "disable_update": True,
                    "disable_pbar": True,
                }
            ],
        )

    def test_transcribe_removes_cjk_token_spaces_but_preserves_english_spaces(self) -> None:
        subject = FunASREnhancedBackend(_build_config())
        subject._model = cast(
            object,
            _FakeModel("哦 等 会 儿 为 什 么 open ai codex 也 有 空 格"),
        )

        result = subject.transcribe(Path("/tmp/voice.wav"), hotwords=[])

        self.assertEqual(result, "哦等会儿为什么open ai codex也有空格")
        self.assertEqual(
            subject._model.generate_kwargs,
            {
                "input": "/tmp/voice.wav",
                "language": "auto",
                "use_itn": True,
                "disable_pbar": True,
                "merge_vad": True,
            },
        )

    def test_transcribe_normalizes_string_result_payload(self) -> None:
        subject = FunASREnhancedBackend(_build_config())
        subject._model = cast(object, _FakeModel(""))

        with patch.object(
            subject._model,
            "generate",
            return_value=["这 是 纯 字 符 串 结 果"],
        ):
            result = subject.transcribe(Path("/tmp/voice.wav"), hotwords=[])

        self.assertEqual(result, "这是纯字符串结果")


if __name__ == "__main__":
    unittest.main()
