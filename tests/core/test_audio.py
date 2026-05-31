from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import final

import numpy as np
from numpy.typing import NDArray

from vibemouse.audio import AudioRecorder, AudioRecording


class _FakeSoundFile:
    def __init__(self) -> None:
        self.paths: list[Path] = []
        self.sample_rates: list[int] = []

    def write(
        self, file: str | Path, data: NDArray[np.float32], samplerate: int
    ) -> None:
        _ = data
        self.paths.append(Path(file))
        self.sample_rates.append(samplerate)


class _FakeSoundDevice:
    def __init__(
        self,
        devices: list[dict[str, object]],
        *,
        default_device: tuple[int, int] | list[int],
    ) -> None:
        self._devices = devices
        self.default = SimpleNamespace(device=default_device)

    def query_devices(self) -> list[dict[str, object]]:
        return self._devices


@final
class _TestableAudioRecorder(AudioRecorder):
    def set_soundfile(self, soundfile: _FakeSoundFile) -> None:
        self._sf = soundfile

    def set_sounddevice(self, sounddevice: _FakeSoundDevice) -> None:
        self._sd = sounddevice

    def prime_recording(self, frame: NDArray[np.float32]) -> None:
        with self._lock:
            self._recording = True
            self._stream = None
            self._frames = [frame]


class AudioRecorderTests(unittest.TestCase):
    @staticmethod
    def _record_once(
        recorder: _TestableAudioRecorder, frame: NDArray[np.float32]
    ) -> AudioRecording:
        recorder.prime_recording(frame)
        recording = recorder.stop_and_save()
        if recording is None:
            raise AssertionError("Expected a recording to be produced")
        return recording

    def test_each_recording_uses_unique_filename(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-tests-") as tmp:
            temp_dir = Path(tmp)
            recorder = _TestableAudioRecorder(
                sample_rate=16000,
                channels=1,
                dtype="float32",
                temp_dir=temp_dir,
            )
            soundfile = _FakeSoundFile()
            recorder.set_soundfile(soundfile)

            frame = np.zeros((160, 1), dtype=np.float32)
            first = self._record_once(recorder, frame)
            second = self._record_once(recorder, frame)

            self.assertNotEqual(first.path, second.path)
            self.assertTrue(first.path.name.startswith("recording_"))
            self.assertTrue(second.path.name.startswith("recording_"))
            self.assertEqual(first.path.suffix, ".wav")
            self.assertEqual(second.path.suffix, ".wav")
            self.assertEqual(soundfile.sample_rates, [16000, 16000])

    def test_prefers_pipewire_session_input_before_raw_alsa_default(self) -> None:
        recorder = _TestableAudioRecorder(
            sample_rate=16000,
            channels=1,
            dtype="float32",
            temp_dir=Path("/tmp"),
        )
        recorder.set_sounddevice(
            _FakeSoundDevice(
                [
                    {
                        "name": "HDA Intel PCH: ALC285 Analog (hw:0,0)",
                        "max_input_channels": 2,
                    },
                    {"name": "pipewire", "max_input_channels": 128},
                    {"name": "pulse", "max_input_channels": 32},
                ],
                default_device=(0, 0),
            )
        )

        self.assertEqual(recorder._resolve_input_device(), 1)

    def test_uses_default_session_input_when_default_device_is_virtual(self) -> None:
        recorder = _TestableAudioRecorder(
            sample_rate=16000,
            channels=1,
            dtype="float32",
            temp_dir=Path("/tmp"),
        )
        recorder.set_sounddevice(
            _FakeSoundDevice(
                [
                    {
                        "name": "HDA Intel PCH: ALC285 Analog (hw:0,0)",
                        "max_input_channels": 2,
                    },
                    {"name": "pipewire", "max_input_channels": 128},
                    {"name": "default", "max_input_channels": 32},
                ],
                default_device=(2, 2),
            )
        )

        self.assertEqual(recorder._resolve_input_device(), 2)

    def test_falls_back_to_raw_input_when_no_session_input_exists(self) -> None:
        recorder = _TestableAudioRecorder(
            sample_rate=16000,
            channels=1,
            dtype="float32",
            temp_dir=Path("/tmp"),
        )
        recorder.set_sounddevice(
            _FakeSoundDevice(
                [
                    {
                        "name": "Monitor of Built-in Audio",
                        "max_input_channels": 2,
                    },
                    {
                        "name": "USB Microphone",
                        "max_input_channels": 1,
                    },
                ],
                default_device=(-1, -1),
            )
        )

        self.assertEqual(recorder._resolve_input_device(), 1)
