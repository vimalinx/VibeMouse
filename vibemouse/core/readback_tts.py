from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from uuid import uuid4


_LOG = logging.getLogger(__name__)
_DEFAULT_VOICE = "en-US-EmmaMultilingualNeural"
_SYNTHESIS_TIMEOUT_S = 90.0
_SYNTHESIS_RETRIES = 1
_PLAYBACK_TIMEOUT_FALLBACK_S = 120.0


class EdgeTTSReadback:
    def __init__(
        self,
        *,
        enabled: bool = False,
        voice: str = _DEFAULT_VOICE,
        temp_dir: Path | None = None,
    ) -> None:
        self._enabled = enabled
        self._voice = voice.strip() or _DEFAULT_VOICE
        self._temp_dir = (
            temp_dir if temp_dir is not None else Path("/tmp") / "vibemouse-readback"
        )
        self._speak_lock = threading.Lock()
        self._warned_missing_edge_tts = False
        self._warned_missing_player = False

    def speak_async(self, text: str) -> None:
        normalized = text.strip()
        if not self._enabled or not normalized:
            return

        worker = threading.Thread(
            target=self.speak,
            args=(normalized,),
            daemon=True,
        )
        worker.start()

    def speak(self, text: str) -> bool:
        normalized = text.strip()
        if not self._enabled or not normalized:
            return False

        with self._speak_lock:
            return self._speak_locked(normalized)

    def _speak_locked(self, text: str) -> bool:
        edge_tts_command = self._resolve_edge_tts_command()
        if edge_tts_command is None:
            if not self._warned_missing_edge_tts:
                _LOG.warning(
                    "Transcript readback skipped: edge-tts command was not found"
                )
                self._warned_missing_edge_tts = True
            return False

        player_command = self._resolve_player_command()
        if player_command is None:
            if not self._warned_missing_player:
                _LOG.warning(
                    "Transcript readback skipped: no audio player found (need mpv or ffplay)"
                )
                self._warned_missing_player = True
            return False

        self._temp_dir.mkdir(parents=True, exist_ok=True)
        media_path = self._temp_dir / f"readback_{uuid4().hex}.mp3"
        try:
            if not self._synthesize_media(
                edge_tts_command=edge_tts_command,
                text=text,
                media_path=media_path,
            ):
                return False

            playback = subprocess.run(
                [*player_command, str(media_path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._playback_timeout_s(media_path, text=text),
            )
            if playback.returncode != 0:
                _LOG.warning(
                    "Transcript readback playback failed: %s",
                    playback.stderr.strip() or playback.stdout.strip() or playback.returncode,
                )
                return False
            return True
        except (OSError, subprocess.TimeoutExpired) as error:
            _LOG.warning("Transcript readback failed: %s", error)
            return False
        finally:
            try:
                media_path.unlink(missing_ok=True)
            except OSError as error:
                _LOG.warning(
                    "Failed to remove readback audio file %s: %s",
                    media_path,
                    error,
                )

    def _synthesize_media(
        self,
        *,
        edge_tts_command: str,
        text: str,
        media_path: Path,
    ) -> bool:
        last_error: str | None = None
        for attempt in range(_SYNTHESIS_RETRIES + 1):
            try:
                media_path.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                synthesis = subprocess.run(
                    [
                        edge_tts_command,
                        "--voice",
                        self._voice,
                        "--text",
                        text,
                        "--write-media",
                        str(media_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_SYNTHESIS_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as error:
                last_error = str(error)
                continue
            except OSError as error:
                last_error = str(error)
                break

            if synthesis.returncode == 0 and media_path.exists():
                return True

            last_error = (
                synthesis.stderr.strip()
                or synthesis.stdout.strip()
                or str(synthesis.returncode)
            )

        if last_error is not None:
            _LOG.warning("Transcript readback synthesis failed: %s", last_error)
        else:
            _LOG.warning(
                "Transcript readback failed: edge-tts did not produce %s",
                media_path,
            )
        return False

    def _playback_timeout_s(self, media_path: Path, *, text: str) -> float:
        duration_s = self._probe_media_duration_s(media_path)
        if duration_s is not None:
            return max(30.0, min(240.0, duration_s + 8.0))
        estimated_s = max(_PLAYBACK_TIMEOUT_FALLBACK_S, min(240.0, len(text) * 1.2))
        return estimated_s

    @staticmethod
    def _probe_media_duration_s(media_path: Path) -> float | None:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        try:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(media_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if probe.returncode != 0:
            return None
        try:
            duration_s = float(probe.stdout.strip())
        except ValueError:
            return None
        if duration_s <= 0:
            return None
        return duration_s

    @staticmethod
    def _resolve_edge_tts_command() -> str | None:
        discovered = shutil.which("edge-tts")
        if discovered:
            return discovered
        fallback = Path.home() / ".local" / "bin" / "edge-tts"
        if fallback.exists():
            return str(fallback)
        return None

    @staticmethod
    def _resolve_player_command() -> list[str] | None:
        mpv = shutil.which("mpv")
        if mpv:
            return [
                mpv,
                "--no-config",
                "--no-video",
                "--really-quiet",
                "--audio-display=no",
            ]

        ffplay = shutil.which("ffplay")
        if ffplay:
            return [
                ffplay,
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
            ]

        return None
