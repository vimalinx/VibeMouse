from __future__ import annotations

import importlib
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from vibemouse.config import AppConfig


class SenseVoiceTranscriber:
    def __init__(self, config: AppConfig) -> None:
        self._config: AppConfig = config
        self._transcriber: _TranscriberProtocol | None = None
        self._transcriber_lock: Lock = Lock()
        self.device_in_use: str = config.device
        self.backend_in_use: str = "unknown"

    def transcribe(self, audio_path: Path) -> str:
        self._ensure_transcriber_loaded()
        if self._transcriber is None:
            raise RuntimeError("SenseVoice transcriber is not initialized")
        return self._transcriber.transcribe(audio_path)

    def prewarm(self) -> None:
        self._ensure_transcriber_loaded()

    def _ensure_transcriber_loaded(self) -> None:
        if self._transcriber is not None:
            return

        with self._transcriber_lock:
            if self._transcriber is not None:
                return

            backend = self._config.transcriber_backend
            if backend == "auto":
                self._build_auto_backend()
                return

            if backend == "funasr":
                self._build_funasr_backend()
                return

            if backend == "funasr_onnx":
                self._build_funasr_onnx_backend()
                return

            raise RuntimeError(
                f"Unsupported backend {backend!r}. Use auto, funasr, or funasr_onnx."
            )

    def _build_auto_backend(self) -> None:
        errors: list[str] = []

        if self._looks_like_intel_npu_device(self._config.device):
            try:
                self._build_funasr_onnx_backend()
                return
            except Exception as error:
                errors.append(f"funasr_onnx: {error}")
                try:
                    self._build_funasr_backend()
                    return
                except Exception as fallback_error:
                    errors.append(f"funasr: {fallback_error}")

        else:
            try:
                self._build_funasr_backend()
                return
            except Exception as error:
                errors.append(f"funasr: {error}")
                try:
                    self._build_funasr_onnx_backend()
                    return
                except Exception as fallback_error:
                    errors.append(f"funasr_onnx: {fallback_error}")

        raise RuntimeError(
            "Failed to initialize any transcriber backend. " + " | ".join(errors)
        )

    def _build_funasr_backend(self) -> None:
        backend = _FunASRBackend(self._config)
        self._transcriber = backend
        self.device_in_use = backend.device_in_use
        self.backend_in_use = "funasr"

    def _build_funasr_onnx_backend(self) -> None:
        backend = _FunASRONNXBackend(self._config)
        self._transcriber = backend
        self.device_in_use = backend.device_in_use
        self.backend_in_use = "funasr_onnx"

    @staticmethod
    def _looks_like_intel_npu_device(device: str) -> bool:
        normalized = device.strip().lower()
        return normalized.startswith("npu") or normalized.startswith("openvino:npu")


class _FunASRBackend:
    def __init__(self, config: AppConfig) -> None:
        self._config: AppConfig = config
        self._model: _SenseModel | None = None
        self._postprocess: _PostprocessFn | None = None
        self._load_lock: Lock = Lock()
        self.device_in_use: str = config.device
        self._ensure_model_loaded()

    def transcribe(self, audio_path: Path) -> str:
        if self._model is None:
            raise RuntimeError("FunASR model is not initialized")

        result = self._model.generate(
            input=str(audio_path),
            cache={},
            language=self._config.language,
            use_itn=self._config.use_itn,
            merge_vad=self._config.merge_vad,
            merge_length_s=self._config.merge_length_s,
            batch_size_s=60,
        )
        if not result:
            return ""

        text_obj = result[0].get("text", "")
        if not isinstance(text_obj, str):
            return ""

        text = text_obj.strip()
        if self._postprocess is None:
            return text
        return self._postprocess(text).strip()

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                model, postprocess = self._create_model(self._config.device)
                self._model = model
                self._postprocess = postprocess
                self.device_in_use = self._config.device
                return
            except Exception as primary_error:
                if (
                    not self._config.fallback_to_cpu
                    or self._config.device.strip().lower() == "cpu"
                ):
                    raise RuntimeError(
                        f"Failed to load FunASR SenseVoice on {self._config.device}: {primary_error}"
                    ) from primary_error

            try:
                model, postprocess = self._create_model("cpu")
            except Exception as cpu_error:
                raise RuntimeError(
                    f"Failed to load FunASR SenseVoice on {self._config.device} and cpu fallback: {cpu_error}"
                ) from cpu_error

            self._model = model
            self._postprocess = postprocess
            self.device_in_use = "cpu"

    def _create_model(self, device: str) -> tuple[_SenseModel, _PostprocessFn]:
        try:
            funasr_module = importlib.import_module("funasr")
            postprocess_module = importlib.import_module(
                "funasr.utils.postprocess_utils"
            )
        except Exception as error:
            raise RuntimeError(
                "FunASR import failed. "
                + f"{error.__class__.__name__}: {error}. "
                + "Ensure dependencies are installed in venv (`pip install -e .`)."
            ) from error

        auto_model_ctor = cast(_AutoModelCtor, getattr(funasr_module, "AutoModel"))
        rich_transcription_postprocess = cast(
            _PostprocessFn,
            getattr(postprocess_module, "rich_transcription_postprocess"),
        )

        kwargs: dict[str, object] = {
            "model": self._config.model_name,
            "trust_remote_code": self._config.trust_remote_code,
            "device": device,
            "disable_update": True,
        }
        if self._config.enable_vad:
            kwargs["vad_model"] = "fsmn-vad"
            kwargs["vad_kwargs"] = {
                "max_single_segment_time": self._config.vad_max_single_segment_ms
            }

        model = auto_model_ctor(**kwargs)
        return model, rich_transcription_postprocess


class _FunASRONNXBackend:
    def __init__(self, config: AppConfig) -> None:
        self._config: AppConfig = config
        self._model: _ONNXSenseVoiceModel | None = None
        self._postprocess: _PostprocessFn | None = None
        self._load_lock: Lock = Lock()
        self.device_in_use: str = "cpu"
        self._ensure_model_loaded()

    def transcribe(self, audio_path: Path) -> str:
        if self._model is None:
            raise RuntimeError("funasr_onnx SenseVoice model is not initialized")
        if self._postprocess is None:
            raise RuntimeError("funasr postprocess function is not initialized")

        textnorm = "withitn" if self._config.use_itn else "woitn"
        result = self._model(
            str(audio_path),
            language=self._config.language,
            textnorm=textnorm,
        )
        if not result:
            return ""

        raw_text = result[0]
        return self._postprocess(raw_text).strip()

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return
            try:
                SenseVoiceSmall = self._load_onnx_class()
                postprocess = self._load_postprocess()
            except Exception as error:
                raise RuntimeError(
                    "funasr_onnx dependency import failed. "
                    + f"{error.__class__.__name__}: {error}. "
                    + "Ensure dependencies are installed in venv (`pip install -e .`)."
                ) from error

            requested_path = self._resolve_onnx_model_dir()
            self._ensure_tokenizer_file(requested_path)
            device_id = self._resolve_onnx_device_id(self._config.device)

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
                return
            except Exception as primary_error:
                if not self._config.fallback_to_cpu:
                    raise RuntimeError(
                        f"Failed to load funasr_onnx backend on {self._config.device}: {primary_error}"
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
                    f"Failed to load funasr_onnx backend on {self._config.device} and cpu fallback: {cpu_error}"
                ) from cpu_error

            self._model = model
            self._postprocess = postprocess
            self.device_in_use = "cpu"

    def _resolve_onnx_model_dir(self) -> Path:
        raw_model = self._config.model_name
        canonical_model = raw_model
        if raw_model == "iic/SenseVoiceSmall":
            canonical_model = "iic/SenseVoiceSmall-onnx"

        if canonical_model.startswith("iic/"):
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
        if not _FunASRONNXBackend._contains_onnx_model(model_dir):
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
        post_module = importlib.import_module("funasr.utils.postprocess_utils")
        return cast(
            _PostprocessFn,
            getattr(post_module, "rich_transcription_postprocess"),
        )


class _TranscriberProtocol(Protocol):
    device_in_use: str

    def transcribe(self, audio_path: Path) -> str: ...


class _SenseResultItem(Protocol):
    def get(self, key: str, default: str = "") -> str | object: ...


class _SenseModel(Protocol):
    def generate(
        self,
        *,
        input: str,
        cache: dict[str, object],
        language: str,
        use_itn: bool,
        merge_vad: bool,
        merge_length_s: int,
        batch_size_s: int,
    ) -> list[_SenseResultItem]: ...


class _AutoModelCtor(Protocol):
    def __call__(self, **kwargs: object) -> _SenseModel: ...


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
