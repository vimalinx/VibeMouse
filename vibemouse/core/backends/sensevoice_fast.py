from __future__ import annotations

import importlib
import logging
import os
import re
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from vibemouse.config import AppConfig
from vibemouse.core.backends.base import BackendStatus, HotwordList


_LOG = logging.getLogger(__name__)
_SENSEVOICE_CONTROL_TOKEN_RE = re.compile(r"<\|[^|>]+\|>")


class SenseVoiceFastBackend:
    backend_id = "sensevoice_fast"

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model: _ONNXSenseVoiceModel | None = None
        self._postprocess: _PostprocessFn | None = None
        self._load_lock = Lock()
        self.device_in_use = "cpu"

    def availability(self) -> BackendStatus:
        try:
            _ = self._resolve_backend_name()
            _ = self._load_onnx_class()
        except Exception as error:
            return BackendStatus(
                backend_id=self.backend_id,
                available=False,
                reason=str(error),
            )
        return BackendStatus(backend_id=self.backend_id, available=True)

    def prewarm(self) -> None:
        self._ensure_model_loaded()

    def transcribe(self, audio_path: Path, *, hotwords: HotwordList) -> str:
        del hotwords
        self._ensure_model_loaded()
        if self._model is None:
            raise RuntimeError("SenseVoice fast backend is not initialized")
        if self._postprocess is None:
            raise RuntimeError("SenseVoice fast postprocess is not initialized")

        textnorm = "withitn" if self._config.use_itn else "woitn"
        result = self._model(
            str(audio_path),
            language=self._config.language,
            textnorm=textnorm,
        )
        if not result:
            return ""

        return self._postprocess(result[0]).strip()

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            requested_path = self._resolve_onnx_model_dir()
            self._ensure_tokenizer_file(requested_path)
            device_id = self._resolve_onnx_device_id(self._config.device)
            SenseVoiceSmall = self._load_onnx_class()
            postprocess = self._load_postprocess()

            try:
                model = SenseVoiceSmall(
                    model_dir=str(requested_path),
                    batch_size=1,
                    device_id=device_id,
                    quantize=True,
                    cache_dir=None,
                )
                self._model = model
                self._postprocess = postprocess
                self.device_in_use = self._resolve_device_label(self._config.device)
                _LOG.info(
                    "Loaded fast backend: backend=%s device_in_use=%s model=%s",
                    self.backend_id,
                    self.device_in_use,
                    requested_path,
                )
                return
            except Exception as primary_error:
                if not self._config.fallback_to_cpu:
                    raise RuntimeError(
                        f"Failed to load {self.backend_id} on {self._config.device}: {primary_error}"
                    ) from primary_error

            try:
                model = SenseVoiceSmall(
                    model_dir=str(requested_path),
                    batch_size=1,
                    device_id="-1",
                    quantize=True,
                    cache_dir=None,
                )
            except Exception as cpu_error:
                raise RuntimeError(
                    f"Failed to load {self.backend_id} on {self._config.device} and cpu fallback: {cpu_error}"
                ) from cpu_error

            self._model = model
            self._postprocess = postprocess
            self.device_in_use = "cpu"
            _LOG.warning(
                "Loaded fast backend with CPU fallback after device load failure"
            )

    def _resolve_backend_name(self) -> str:
        backend = self._config.transcriber_backend.strip().lower()
        if backend in {"auto", "funasr"}:
            _LOG.warning(
                "Backend %r is deprecated for fast mode; using 'funasr_onnx' instead",
                backend,
            )
            return "funasr_onnx"
        if backend != "funasr_onnx":
            raise RuntimeError(f"Unsupported fast backend {backend!r}. Use funasr_onnx.")
        return backend

    def _resolve_onnx_model_dir(self) -> Path:
        _ = self._resolve_backend_name()
        raw_model = self._config.model_name
        canonical_model = raw_model
        if raw_model == "iic/SenseVoiceSmall":
            canonical_model = "iic/SenseVoiceSmall-onnx"

        if canonical_model.startswith("iic/"):
            cached_model_dir = self._resolve_cached_modelscope_dir(canonical_model)
            if cached_model_dir is not None:
                return cached_model_dir
            return self._download_modelscope_snapshot(canonical_model)

        path_candidate = Path(canonical_model)
        if not path_candidate.exists():
            return path_candidate

        if self._contains_onnx_model(path_candidate):
            return path_candidate

        raise RuntimeError(
            f"ONNX model directory {path_candidate} exists but model_quant.onnx/model.onnx is missing"
        )

    @staticmethod
    def _contains_onnx_model(model_dir: Path) -> bool:
        return (model_dir / "model_quant.onnx").exists() or (
            model_dir / "model.onnx"
        ).exists()

    @staticmethod
    def _resolve_cached_modelscope_dir(model_id: str) -> Path | None:
        owner, _, repo = model_id.partition("/")
        if not owner or not repo:
            return None

        cache_home = Path(
            os.getenv("XDG_CACHE_HOME", str(Path.home() / ".cache"))
        ).expanduser()
        candidate = cache_home / "modelscope" / "hub" / "models" / owner / repo
        if not candidate.exists():
            return None
        if not SenseVoiceFastBackend._contains_onnx_model(candidate):
            return None
        return candidate

    @staticmethod
    def _download_modelscope_snapshot(model_id: str) -> Path:
        try:
            snapshot_mod = importlib.import_module("modelscope.hub.snapshot_download")
        except Exception as error:
            raise RuntimeError(
                "modelscope is required to download ONNX model snapshots"
            ) from error

        snapshot_download = cast(
            _SnapshotDownloadFn,
            getattr(snapshot_mod, "snapshot_download"),
        )
        snapshot_path = snapshot_download(model_id)
        model_dir = Path(snapshot_path)
        if not model_dir.exists():
            raise RuntimeError(f"Downloaded model path does not exist: {snapshot_path}")
        if not SenseVoiceFastBackend._contains_onnx_model(model_dir):
            raise RuntimeError(
                f"Downloaded model {model_id} missing model_quant.onnx/model.onnx"
            )
        return model_dir

    @staticmethod
    def _resolve_onnx_device_id(device: str) -> str:
        normalized = device.strip().lower()
        if normalized == "cpu":
            return "-1"
        if normalized.startswith("cuda"):
            parts = normalized.split(":", 1)
            return parts[1] if len(parts) > 1 and parts[1] else "0"
        return "-1"

    @staticmethod
    def _resolve_device_label(device: str) -> str:
        normalized = device.strip().lower()
        if normalized.startswith("cuda"):
            return normalized
        return "cpu"

    def _ensure_tokenizer_file(self, model_dir: Path) -> None:
        target = model_dir / "chn_jpn_yue_eng_ko_spectok.bpe.model"
        if target.exists():
            return

        fallback = (
            Path.home()
            / ".cache/modelscope/hub/models/iic/SenseVoiceSmall/chn_jpn_yue_eng_ko_spectok.bpe.model"
        )
        if fallback.exists():
            model_dir.mkdir(parents=True, exist_ok=True)
            _ = target.write_bytes(fallback.read_bytes())
            return

        raise RuntimeError(
            "Tokenizer file chn_jpn_yue_eng_ko_spectok.bpe.model is missing and no fallback was found"
        )

    @staticmethod
    def _load_onnx_class() -> _ONNXSenseVoiceCtor:
        module = importlib.import_module("funasr_onnx")
        return cast(_ONNXSenseVoiceCtor, getattr(module, "SenseVoiceSmall"))

    @staticmethod
    def _load_postprocess() -> _PostprocessFn:
        try:
            post_module = importlib.import_module("funasr.utils.postprocess_utils")
            return cast(
                _PostprocessFn,
                getattr(post_module, "rich_transcription_postprocess"),
            )
        except Exception:
            try:
                post_module = importlib.import_module(
                    "funasr_onnx.utils.postprocess_utils"
                )
                return cast(
                    _PostprocessFn,
                    getattr(post_module, "rich_transcription_postprocess"),
                )
            except Exception:
                return _strip_sensevoice_control_tokens


def _strip_sensevoice_control_tokens(text: str) -> str:
    cleaned = _SENSEVOICE_CONTROL_TOKEN_RE.sub("", text)
    return " ".join(cleaned.split()).strip()


class _PostprocessFn(Protocol):
    def __call__(self, text: str) -> str: ...


class _ONNXSenseVoiceModel(Protocol):
    def __call__(
        self,
        wav_content: str,
        *,
        language: str,
        textnorm: str,
    ) -> list[str]: ...


class _ONNXSenseVoiceCtor(Protocol):
    def __call__(
        self,
        *,
        model_dir: str,
        batch_size: int,
        device_id: str,
        quantize: bool,
        cache_dir: str | None,
    ) -> _ONNXSenseVoiceModel: ...


class _SnapshotDownloadFn(Protocol):
    def __call__(self, model_id: str) -> str: ...
