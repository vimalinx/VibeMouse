from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vibemouse.core.readback_tts import EdgeTTSReadback


class EdgeTTSReadbackTests(unittest.TestCase):
    def test_speak_returns_false_when_disabled(self) -> None:
        subject = EdgeTTSReadback(enabled=False)

        self.assertFalse(subject.speak("hello world"))

    def test_speak_uses_edge_tts_and_mpv_when_available(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
            calls.append(cmd)
            if "--write-media" in cmd:
                media_path = Path(cmd[cmd.index("--write-media") + 1])
                media_path.parent.mkdir(parents=True, exist_ok=True)
                _ = media_path.write_bytes(b"mp3")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory(prefix="vibemouse-readback-") as tmp:
            subject = EdgeTTSReadback(
                enabled=True,
                voice="en-US-EmmaMultilingualNeural",
                temp_dir=Path(tmp),
            )
            with (
                patch(
                    "vibemouse.core.readback_tts.shutil.which",
                    side_effect=lambda name: {
                        "edge-tts": "/usr/bin/edge-tts",
                        "mpv": "/usr/bin/mpv",
                    }.get(name),
                ),
                patch.object(
                    EdgeTTSReadback,
                    "_playback_timeout_s",
                    return_value=60.0,
                ),
                patch("vibemouse.core.readback_tts.subprocess.run", side_effect=fake_run),
            ):
                ok = subject.speak("你好，世界。")

        self.assertTrue(ok)
        self.assertEqual(calls[0][:5], ["/usr/bin/edge-tts", "--voice", "en-US-EmmaMultilingualNeural", "--text", "你好，世界。"])
        self.assertIn("--write-media", calls[0])
        self.assertEqual(
            calls[1][:5],
            ["/usr/bin/mpv", "--no-config", "--no-video", "--really-quiet", "--audio-display=no"],
        )

    def test_speak_falls_back_to_ffplay_when_mpv_is_missing(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
            calls.append(cmd)
            if "--write-media" in cmd:
                media_path = Path(cmd[cmd.index("--write-media") + 1])
                media_path.parent.mkdir(parents=True, exist_ok=True)
                _ = media_path.write_bytes(b"mp3")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory(prefix="vibemouse-readback-") as tmp:
            subject = EdgeTTSReadback(enabled=True, temp_dir=Path(tmp))
            with (
                patch(
                    "vibemouse.core.readback_tts.shutil.which",
                    side_effect=lambda name: {
                        "edge-tts": "/usr/bin/edge-tts",
                        "ffplay": "/usr/bin/ffplay",
                    }.get(name),
                ),
                patch.object(
                    EdgeTTSReadback,
                    "_playback_timeout_s",
                    return_value=60.0,
                ),
                patch("vibemouse.core.readback_tts.subprocess.run", side_effect=fake_run),
            ):
                ok = subject.speak("hello world")

        self.assertTrue(ok)
        self.assertEqual(
            calls[1][:5],
            ["/usr/bin/ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
        )

    def test_playback_timeout_uses_probed_media_duration(self) -> None:
        subject = EdgeTTSReadback(enabled=True)

        with patch.object(
            EdgeTTSReadback,
            "_probe_media_duration_s",
            return_value=12.5,
        ):
            timeout_s = subject._playback_timeout_s(Path("/tmp/test.mp3"), text="hello")

        self.assertEqual(timeout_s, 30.0)

    def test_playback_timeout_falls_back_when_duration_probe_fails(self) -> None:
        subject = EdgeTTSReadback(enabled=True)

        with patch.object(
            EdgeTTSReadback,
            "_probe_media_duration_s",
            return_value=None,
        ):
            timeout_s = subject._playback_timeout_s(
                Path("/tmp/test.mp3"),
                text="This is a much longer playback sample",
            )

        self.assertEqual(timeout_s, 120.0)
