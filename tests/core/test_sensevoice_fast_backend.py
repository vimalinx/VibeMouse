from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vibemouse.config import build_default_config_document, config_document_to_app_config
from vibemouse.core.backends.sensevoice_fast import SenseVoiceFastBackend


def _build_config():
    return config_document_to_app_config(build_default_config_document())


class SenseVoiceFastBackendModelResolutionTests(unittest.TestCase):
    def test_prefers_local_modelscope_cache_before_download(self) -> None:
        config = _build_config()
        subject = SenseVoiceFastBackend(config)

        with tempfile.TemporaryDirectory(prefix="vibemouse-cache-") as tmp:
            cache_root = Path(tmp) / "cache"
            model_dir = (
                cache_root
                / "modelscope"
                / "hub"
                / "models"
                / "iic"
                / "SenseVoiceSmall-onnx"
            )
            model_dir.mkdir(parents=True, exist_ok=True)
            _ = (model_dir / "model_quant.onnx").write_bytes(b"onnx")

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache_root)}, clear=False),
                patch.object(
                    SenseVoiceFastBackend,
                    "_download_modelscope_snapshot",
                    side_effect=AssertionError("should not download when cache exists"),
                ),
            ):
                resolved = subject._resolve_onnx_model_dir()

        self.assertEqual(resolved, model_dir)

    def test_downloads_when_local_modelscope_cache_is_incomplete(self) -> None:
        config = _build_config()
        subject = SenseVoiceFastBackend(config)

        with tempfile.TemporaryDirectory(prefix="vibemouse-cache-") as tmp:
            cache_root = Path(tmp) / "cache"
            incomplete_dir = (
                cache_root
                / "modelscope"
                / "hub"
                / "models"
                / "iic"
                / "SenseVoiceSmall-onnx"
            )
            incomplete_dir.mkdir(parents=True, exist_ok=True)
            _ = (incomplete_dir / "README.md").write_text("missing model", encoding="utf-8")
            downloaded_dir = Path(tmp) / "downloaded-model"

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache_root)}, clear=False),
                patch.object(
                    SenseVoiceFastBackend,
                    "_download_modelscope_snapshot",
                    return_value=downloaded_dir,
                ) as download_mock,
            ):
                resolved = subject._resolve_onnx_model_dir()

        self.assertEqual(resolved, downloaded_dir)
        download_mock.assert_called_once_with("iic/SenseVoiceSmall-onnx")
