#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _build_model(*, model: str, device: str, use_vad: bool, trust_remote_code: bool):
    try:
        from funasr import AutoModel
    except Exception as error:  # pragma: no cover
        raise RuntimeError(
            f"FunASR import failed: {error}. Please install requirements.txt"
        ) from error

    kwargs: dict[str, Any] = {
        "model": model,
        "device": device,
        "trust_remote_code": trust_remote_code,
        "disable_update": True,
    }
    if use_vad:
        kwargs["vad_model"] = "fsmn-vad"
        kwargs["vad_kwargs"] = {"max_single_segment_time": 30000}

    return AutoModel(**kwargs)


def _transcribe_audio(
    *,
    audio_path: Path,
    model_name: str,
    device: str,
    language: str,
    use_itn: bool,
    use_vad: bool,
    trust_remote_code: bool,
) -> tuple[str, str]:
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
    except Exception as error:  # pragma: no cover
        raise RuntimeError(
            f"FunASR postprocess import failed: {error}. Please install requirements.txt"
        ) from error

    model = None
    device_in_use = device
    primary_error: Exception | None = None
    try:
        model = _build_model(
            model=model_name,
            device=device,
            use_vad=use_vad,
            trust_remote_code=trust_remote_code,
        )
    except Exception as error:
        primary_error = error
        if device.strip().lower() != "cpu":
            model = _build_model(
                model=model_name,
                device="cpu",
                use_vad=use_vad,
                trust_remote_code=trust_remote_code,
            )
            device_in_use = "cpu"
        else:
            raise

    if model is None:
        raise RuntimeError(f"Failed to load model on {device}: {primary_error}")

    result = model.generate(
        input=str(audio_path),
        cache={},
        language=language,
        use_itn=use_itn,
        merge_vad=True,
        merge_length_s=15,
        batch_size_s=60,
    )
    if not result:
        return "", device_in_use

    raw_text = result[0].get("text", "")
    if not isinstance(raw_text, str):
        return "", device_in_use

    return rich_transcription_postprocess(raw_text).strip(), device_in_use


def _record_to_wav(*, seconds: float, sample_rate: int, channels: int) -> tuple[Path, float]:
    try:
        import sounddevice as sd
        import soundfile as sf
    except Exception as error:  # pragma: no cover
        raise RuntimeError(
            f"Audio dependencies missing: {error}. Please install requirements.txt"
        ) from error

    frame_count = max(1, int(seconds * sample_rate))
    with tempfile.NamedTemporaryFile(prefix="openclaw_stt_", suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    start = time.monotonic()
    audio = sd.rec(
        frame_count,
        samplerate=sample_rate,
        channels=channels,
        dtype="float32",
    )
    sd.wait()
    duration_s = time.monotonic() - start
    sf.write(str(out_path), audio, sample_rate)
    return out_path, duration_s


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openclaw-stt-cli")
    parser.add_argument("--audio-path", type=str, default="")
    parser.add_argument("--record-seconds", type=float, default=5.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--model", type=str, default="iic/SenseVoiceSmall")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--language", type=str, default="auto")
    parser.add_argument("--use-itn", action="store_true")
    parser.add_argument("--use-vad", action="store_true")
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    record_seconds = max(0.3, float(args.record_seconds))
    sample_rate = max(8000, int(args.sample_rate))
    channels = max(1, int(args.channels))

    temp_audio = False
    audio_path = Path(args.audio_path).expanduser().resolve() if args.audio_path else None
    if audio_path is None:
        try:
            audio_path, recorded_duration = _record_to_wav(
                seconds=record_seconds,
                sample_rate=sample_rate,
                channels=channels,
            )
        except Exception as error:
            if args.json:
                _emit_json({"ok": False, "error": str(error)})
            else:
                print(f"error: {error}")
            return 1
        temp_audio = True
    else:
        recorded_duration = None
        if not audio_path.exists():
            message = f"audio file not found: {audio_path}"
            if args.json:
                _emit_json({"ok": False, "error": message})
            else:
                print(f"error: {message}")
            return 1

    try:
        text, device_in_use = _transcribe_audio(
            audio_path=audio_path,
            model_name=args.model,
            device=args.device,
            language=args.language,
            use_itn=bool(args.use_itn),
            use_vad=bool(args.use_vad),
            trust_remote_code=bool(args.trust_remote_code),
        )
    except Exception as error:
        if args.json:
            _emit_json({"ok": False, "error": str(error)})
        else:
            print(f"error: {error}")
        return_code = 1
    else:
        payload = {
            "ok": True,
            "text": text,
            "audio_path": str(audio_path),
            "device_in_use": device_in_use,
            "recorded_duration_s": recorded_duration,
        }
        if args.json:
            _emit_json(payload)
        else:
            print(text)
        return_code = 0
    finally:
        if temp_audio and audio_path is not None:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
