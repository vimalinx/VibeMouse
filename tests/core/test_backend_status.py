from __future__ import annotations

import unittest

from vibemouse.config import build_default_config_document, config_document_to_app_config
from vibemouse.core.backend_status import collect_backend_statuses
from vibemouse.core.backends.base import BackendStatus
from vibemouse.core.transcriber import SenseVoiceTranscriber


def _build_config():
    return config_document_to_app_config(build_default_config_document())


class _FakeBackend:
    def __init__(
        self,
        *,
        backend_id: str,
        available: bool,
        reason: str | None = None,
    ) -> None:
        self.backend_id = backend_id
        self.device_in_use = "cpu"
        self._available = available
        self._reason = reason

    def availability(self) -> BackendStatus:
        return BackendStatus(
            backend_id=self.backend_id,
            available=self._available,
            reason=self._reason,
        )

    def prewarm(self) -> None:
        return None

    def transcribe(self, audio_path, *, hotwords):
        raise AssertionError("transcribe should not be called while collecting status")


class BackendStatusCollectionTests(unittest.TestCase):
    def test_backend_status_reports_fast_and_enhanced_availability(self) -> None:
        config = _build_config()
        subject = SenseVoiceTranscriber(
            config,
            backend_factories={
                "fast": lambda _config: _FakeBackend(
                    backend_id="sensevoice_fast",
                    available=True,
                ),
                "enhanced": lambda _config: _FakeBackend(
                    backend_id="funasr_enhanced",
                    available=True,
                ),
            },
        )

        statuses = collect_backend_statuses(subject)

        self.assertEqual(statuses["default"].backend_id, "sensevoice_fast")
        self.assertTrue(statuses["default"].available)
        self.assertIsNone(statuses["default"].reason)

    def test_unavailable_backend_reports_reason_string(self) -> None:
        config = _build_config()
        config.profiles["default"] = "enhanced"
        subject = SenseVoiceTranscriber(
            config,
            backend_factories={
                "fast": lambda _config: _FakeBackend(
                    backend_id="sensevoice_fast",
                    available=True,
                ),
                "enhanced": lambda _config: _FakeBackend(
                    backend_id="funasr_enhanced",
                    available=False,
                    reason="funasr package is not installed",
                ),
            },
        )

        statuses = collect_backend_statuses(subject)

        self.assertEqual(statuses["default"].backend_id, "funasr_enhanced")
        self.assertFalse(statuses["default"].available)
        self.assertEqual(
            statuses["default"].reason,
            "funasr package is not installed",
        )
