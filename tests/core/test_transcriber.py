from __future__ import annotations

import unittest
from collections.abc import Callable
from pathlib import Path

from vibemouse.config import build_default_config_document, config_document_to_app_config
from vibemouse.core.backends.base import BackendStatus, BackendUnavailableError
from vibemouse.core.transcriber import SenseVoiceTranscriber


def _build_config():
    return config_document_to_app_config(build_default_config_document())


class _FakeBackend:
    def __init__(
        self,
        *,
        backend_id: str,
        device_in_use: str,
        result_text: str = "",
        available: bool = True,
        reason: str | None = None,
    ) -> None:
        self.backend_id = backend_id
        self.device_in_use = device_in_use
        self._result_text = result_text
        self._available = available
        self._reason = reason
        self.calls: list[tuple[Path, list[tuple[str, int]]]] = []
        self.prewarm_calls = 0

    def availability(self) -> BackendStatus:
        return BackendStatus(
            backend_id=self.backend_id,
            available=self._available,
            reason=self._reason,
        )

    def transcribe(
        self,
        audio_path: Path,
        *,
        hotwords: list[tuple[str, int]],
    ) -> str:
        self.calls.append((audio_path, hotwords))
        return self._result_text

    def prewarm(self) -> None:
        self.prewarm_calls += 1


class SenseVoiceTranscriberRoutingTests(unittest.TestCase):
    def test_router_uses_fast_backend_for_default_profile(self) -> None:
        config = _build_config()
        fast_backend = _FakeBackend(
            backend_id="sensevoice_fast",
            device_in_use="cpu",
            result_text="fast result",
        )
        enhanced_backend = _FakeBackend(
            backend_id="funasr_enhanced",
            device_in_use="cuda:0",
            result_text="enhanced result",
        )
        subject = SenseVoiceTranscriber(
            config,
            backend_factories={
                "fast": lambda _config: fast_backend,
                "enhanced": lambda _config: enhanced_backend,
            },
        )

        result = subject.transcribe(
            Path("/tmp/default.wav"),
            output_target="default",
            hotwords=[("codex", 8)],
        )

        self.assertEqual(result, "fast result")
        self.assertEqual(
            fast_backend.calls,
            [(Path("/tmp/default.wav"), [("codex", 8)])],
        )
        self.assertEqual(enhanced_backend.calls, [])
        self.assertEqual(subject.profile_in_use, "fast")
        self.assertEqual(subject.backend_in_use, "sensevoice_fast")
        self.assertEqual(subject.device_in_use, "cpu")

    def test_router_uses_enhanced_backend_for_default_profile_when_configured(self) -> None:
        config = _build_config()
        config.profiles["default"] = "enhanced"
        fast_backend = _FakeBackend(
            backend_id="sensevoice_fast",
            device_in_use="cpu",
            result_text="fast result",
        )
        enhanced_backend = _FakeBackend(
            backend_id="funasr_enhanced",
            device_in_use="cuda:0",
            result_text="enhanced result",
        )
        subject = SenseVoiceTranscriber(
            config,
            backend_factories={
                "fast": lambda _config: fast_backend,
                "enhanced": lambda _config: enhanced_backend,
            },
        )

        result = subject.transcribe(
            Path("/tmp/enhanced.wav"),
            output_target="default",
            hotwords=[("codex", 8), ("claude code", 7)],
        )

        self.assertEqual(result, "enhanced result")
        self.assertEqual(fast_backend.calls, [])
        self.assertEqual(
            enhanced_backend.calls,
            [(Path("/tmp/enhanced.wav"), [("codex", 8), ("claude code", 7)])],
        )
        self.assertEqual(subject.profile_in_use, "enhanced")
        self.assertEqual(subject.backend_in_use, "funasr_enhanced")
        self.assertEqual(subject.device_in_use, "cuda:0")

    def test_router_reports_unavailable_backend_without_silent_downgrade(self) -> None:
        config = _build_config()
        config.profiles["default"] = "enhanced"
        fast_backend = _FakeBackend(
            backend_id="sensevoice_fast",
            device_in_use="cpu",
            result_text="fast result",
        )
        enhanced_backend = _FakeBackend(
            backend_id="funasr_enhanced",
            device_in_use="cuda:0",
            available=False,
            reason="funasr package is not installed",
        )
        subject = SenseVoiceTranscriber(
            config,
            backend_factories={
                "fast": lambda _config: fast_backend,
                "enhanced": lambda _config: enhanced_backend,
            },
        )

        with self.assertRaises(BackendUnavailableError) as context:
            subject.transcribe(
                Path("/tmp/enhanced.wav"),
                output_target="default",
                hotwords=[("codex", 8)],
            )

        self.assertEqual(context.exception.backend_id, "funasr_enhanced")
        self.assertIn("funasr package is not installed", str(context.exception))
        self.assertEqual(fast_backend.calls, [])
        self.assertEqual(enhanced_backend.calls, [])
