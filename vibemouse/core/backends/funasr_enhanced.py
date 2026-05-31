from __future__ import annotations

import importlib
import re
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from vibemouse.config import AppConfig
from vibemouse.core.backends.base import (
    BackendStatus,
    BackendUnavailableError,
    HotwordList,
)


_DEFAULT_ENHANCED_MODEL = "paraformer-zh"
_DEFAULT_PUNCTUATION_MODEL = "ct-punc"
_DEFAULT_VAD_MODEL = "fsmn-vad"
_SPACE_AROUND_CJK_RE = re.compile(r"(?<=[\u3400-\u9fff])\s+|\s+(?=[\u3400-\u9fff])")
_WHITESPACE_RE = re.compile(r"\s+")


class FunASREnhancedBackend:
    backend_id = "funasr_enhanced"

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._model: _FunASRModel | None = None
        self._load_lock = Lock()
        self.device_in_use = _normalize_device_label(config.device)

    def availability(self) -> BackendStatus:
        try:
            _ = self._load_automodel_ctor()
        except Exception as error:
            return BackendStatus(
                backend_id=self.backend_id,
                available=False,
                reason=f"funasr dependency unavailable: {error}",
            )
        return BackendStatus(backend_id=self.backend_id, available=True)

    def prewarm(self) -> None:
        self._ensure_model_loaded()

    def transcribe(self, audio_path: Path, *, hotwords: HotwordList) -> str:
        self._ensure_model_loaded()
        if self._model is None:
            raise RuntimeError("Enhanced backend is not initialized")

        generate_kwargs: dict[str, object] = {
            "input": str(audio_path),
            "language": self._config.language,
            "use_itn": self._config.use_itn,
            "disable_pbar": True,
        }
        if self._config.enable_vad:
            generate_kwargs["merge_vad"] = self._config.merge_vad
        hotword_payload = _format_hotwords(hotwords)
        if hotword_payload:
            generate_kwargs["hotword"] = hotword_payload

        result = self._model.generate(**generate_kwargs)
        if not result:
            return ""

        first = result[0]
        if isinstance(first, dict):
            text = first.get("text", "")
        else:
            text = first
        return _normalize_transcript_spacing(str(text))

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return
            AutoModel = self._load_automodel_ctor()
            model_kwargs: dict[str, object] = {
                "model": self._resolve_model_name(),
                "punc_model": _DEFAULT_PUNCTUATION_MODEL,
                "device": self.device_in_use,
                "disable_update": True,
                "disable_pbar": True,
            }
            if self._config.enable_vad:
                model_kwargs["vad_model"] = _DEFAULT_VAD_MODEL
                model_kwargs["vad_kwargs"] = {
                    "max_single_segment_time": self._config.vad_max_single_segment_ms,
                }
                model_kwargs["merge_length_s"] = self._config.merge_length_s
            try:
                self._model = AutoModel(**model_kwargs)
            except Exception as error:
                raise BackendUnavailableError(
                    backend_id=self.backend_id,
                    reason=f"failed to initialize model: {error}",
                ) from error

    def _resolve_model_name(self) -> str:
        current = self._config.model_name.strip()
        if current in {"", "iic/SenseVoiceSmall", "iic/SenseVoiceSmall-onnx"}:
            return _DEFAULT_ENHANCED_MODEL
        return current

    @staticmethod
    def _load_automodel_ctor() -> _AutoModelCtor:
        module = importlib.import_module("funasr")
        return cast(_AutoModelCtor, getattr(module, "AutoModel"))


def _format_hotwords(hotwords: HotwordList) -> str | None:
    if not hotwords:
        return None

    deduped: list[str] = []
    seen: set[str] = set()
    for phrase, _weight in sorted(hotwords, key=lambda item: (-item[1], item[0].casefold())):
        normalized = phrase.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)

    if not deduped:
        return None
    return "\n".join(deduped)


def _normalize_transcript_spacing(text: str) -> str:
    compacted = _WHITESPACE_RE.sub(" ", text).strip()
    return _SPACE_AROUND_CJK_RE.sub("", compacted)


def _normalize_device_label(device: str) -> str:
    normalized = device.strip().lower()
    if normalized.startswith("cuda"):
        return normalized
    return "cpu"


class _FunASRModel(Protocol):
    def generate(self, **kwargs: object) -> list[dict[str, object] | str]: ...


class _AutoModelCtor(Protocol):
    def __call__(self, **kwargs: object) -> _FunASRModel: ...
