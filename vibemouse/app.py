from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Literal

from vibemouse.audio import AudioRecorder, AudioRecording
from vibemouse.config import AppConfig
from vibemouse.mouse_listener import SideButtonListener
from vibemouse.output import TextOutput
from vibemouse.system_integration import SystemIntegration, create_system_integration
from vibemouse.transcriber import SenseVoiceTranscriber


TranscriptionTarget = Literal["default", "openclaw"]


class VoiceMouseApp:
    def __init__(self, config: AppConfig) -> None:
        if config.front_button == config.rear_button:
            raise ValueError("Front and rear side buttons must be different")

        self._config: AppConfig = config
        self._system_integration: SystemIntegration = create_system_integration()
        self._recorder: AudioRecorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            dtype=config.dtype,
            temp_dir=config.temp_dir,
        )
        self._transcriber: SenseVoiceTranscriber = SenseVoiceTranscriber(config)
        self._output: TextOutput = TextOutput(
            system_integration=self._system_integration,
            openclaw_command=config.openclaw_command,
            openclaw_agent=config.openclaw_agent,
            openclaw_timeout_s=config.openclaw_timeout_s,
            openclaw_retries=config.openclaw_retries,
        )
        self._listener: SideButtonListener = SideButtonListener(
            on_front_press=self._on_front_press,
            on_rear_press=self._on_rear_press,
            on_gesture=self._on_gesture,
            front_button=config.front_button,
            rear_button=config.rear_button,
            debounce_s=config.button_debounce_ms / 1000.0,
            gestures_enabled=config.gestures_enabled,
            gesture_trigger_button=config.gesture_trigger_button,
            gesture_threshold_px=config.gesture_threshold_px,
            gesture_freeze_pointer=config.gesture_freeze_pointer,
            gesture_restore_cursor=config.gesture_restore_cursor,
            system_integration=self._system_integration,
        )
        self._stop_event: threading.Event = threading.Event()
        self._transcribe_lock: threading.Lock = threading.Lock()
        self._workers_lock: threading.Lock = threading.Lock()
        self._workers: set[threading.Thread] = set()
        self._prewarm_started: bool = False

    def run(self) -> None:
        self._listener.start()
        self._set_recording_status(False)
        print(
            "VibeMouse ready. "
            + f"Model={self._config.model_name}, preferred_device={self._config.device}, "
            + f"backend={self._config.transcriber_backend}, auto_paste={self._config.auto_paste}, "
            + f"enter_mode={self._config.enter_mode}, debounce_ms={self._config.button_debounce_ms}, "
            + f"front_button={self._config.front_button}, rear_button={self._config.rear_button}, "
            + f"gestures_enabled={self._config.gestures_enabled}, "
            + f"gesture_trigger={self._config.gesture_trigger_button}, "
            + f"gesture_threshold_px={self._config.gesture_threshold_px}, "
            + f"gesture_freeze_pointer={self._config.gesture_freeze_pointer}, "
            + f"gesture_restore_cursor={self._config.gesture_restore_cursor}, "
            + f"prewarm_on_start={self._config.prewarm_on_start}, "
            + f"prewarm_delay_s={self._config.prewarm_delay_s}. "
            + "Press side-front to start/stop recording. While recording, side-rear sends transcript to OpenClaw; otherwise side-rear sends Enter."
        )
        self._maybe_prewarm_transcriber()
        try:
            _ = self._stop_event.wait()
        except KeyboardInterrupt:
            self._stop_event.set()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._listener.stop()
        self._recorder.cancel()
        self._set_recording_status(False)
        with self._workers_lock:
            workers = list(self._workers)
        still_running: list[threading.Thread] = []
        for worker in workers:
            worker.join(timeout=5)
            if worker.is_alive():
                still_running.append(worker)
        if still_running:
            print(
                f"Shutdown warning: {len(still_running)} transcription worker(s) are still running"
            )

    def _on_front_press(self) -> None:
        if not self._recorder.is_recording:
            try:
                self._recorder.start()
                self._set_recording_status(True)
                print("Recording started")
            except Exception as error:
                self._set_recording_status(False)
                print(f"Failed to start recording: {error}")
            return

        try:
            recording = self._stop_recording()
        except Exception as error:
            print(f"Failed to stop recording: {error}")
            return

        if recording is None:
            return

        self._start_transcription_worker(recording, output_target="default")

    def _on_rear_press(self) -> None:
        if self._recorder.is_recording:
            try:
                recording = self._stop_recording()
            except Exception as error:
                print(f"Failed to stop recording from rear button: {error}")
                return

            if recording is None:
                return

            print("Recording stopped by rear button, sending transcript to OpenClaw")
            self._start_transcription_worker(recording, output_target="openclaw")
            return

        try:
            self._output.send_enter(mode=self._config.enter_mode)
            if self._config.enter_mode == "none":
                print("Enter key handling disabled (enter_mode=none)")
            else:
                print("Enter key sent")
        except Exception as error:
            print(f"Failed to send Enter: {error}")

    def _on_gesture(self, direction: str) -> None:
        action = self._resolve_gesture_action(direction)
        if action == "noop":
            print(f"Gesture '{direction}' recognized with no action configured")
            return

        if action == "record_toggle":
            print(f"Gesture '{direction}' -> toggle recording")
            self._on_front_press()
            return

        if action == "send_enter":
            mode = self._config.enter_mode
            if mode == "none":
                mode = "enter"
            try:
                self._output.send_enter(mode=mode)
                print(f"Gesture '{direction}' -> send enter ({mode})")
            except Exception as error:
                print(f"Gesture '{direction}' failed to send enter: {error}")
            return

        if action == "workspace_left":
            if self._switch_workspace("left"):
                print(f"Gesture '{direction}' -> switch workspace left")
            else:
                print(f"Gesture '{direction}' failed to switch workspace left")
            return

        if action == "workspace_right":
            if self._switch_workspace("right"):
                print(f"Gesture '{direction}' -> switch workspace right")
            else:
                print(f"Gesture '{direction}' failed to switch workspace right")
            return

        print(f"Gesture '{direction}' mapped to unknown action '{action}'")

    def _resolve_gesture_action(self, direction: str) -> str:
        mapping = {
            "up": self._config.gesture_up_action,
            "down": self._config.gesture_down_action,
            "left": self._config.gesture_left_action,
            "right": self._config.gesture_right_action,
        }
        return mapping.get(direction, "noop")

    def _switch_workspace(self, direction: str) -> bool:
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                return bool(system_integration.switch_workspace(direction))
            except Exception:
                return False

        workspace_arg = "e-1" if direction == "left" else "e+1"
        try:
            proc = subprocess.run(
                ["hyprctl", "dispatch", "workspace", workspace_arg],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return proc.returncode == 0 and proc.stdout.strip() == "ok"

    def _stop_recording(self) -> AudioRecording | None:
        try:
            recording = self._recorder.stop_and_save()
        except Exception as error:
            self._set_recording_status(False)
            raise RuntimeError(error) from error

        self._set_recording_status(False)
        if recording is None:
            print("Recording was empty and has been discarded")
            return None
        return recording

    def _start_transcription_worker(
        self,
        recording: AudioRecording,
        *,
        output_target: TranscriptionTarget,
    ) -> None:
        worker = threading.Thread(
            target=self._transcribe_and_output,
            args=(recording, output_target),
            daemon=True,
        )
        with self._workers_lock:
            self._workers.add(worker)
        worker.start()

    def _transcribe_and_output(
        self,
        recording: AudioRecording,
        output_target: TranscriptionTarget,
    ) -> None:
        current = threading.current_thread()
        try:
            print(f"Recording stopped ({recording.duration_s:.1f}s), transcribing...")
            with self._transcribe_lock:
                text = self._transcriber.transcribe(recording.path)

            if not text:
                print("No speech recognized")
                return

            if output_target == "openclaw":
                dispatch = self._output.send_to_openclaw_result(text)
                route = dispatch.route
                dispatch_reason = dispatch.reason
            else:
                route = self._output.inject_or_clipboard(
                    text,
                    auto_paste=self._config.auto_paste,
                )
                dispatch_reason = "n/a"

            device = self._transcriber.device_in_use
            backend = self._transcriber.backend_in_use

            if output_target == "openclaw":
                if route == "openclaw":
                    print(
                        f"Transcribed with {backend} on {device}, sent to OpenClaw ({dispatch_reason})"
                    )
                elif route == "clipboard":
                    print(
                        f"Transcribed with {backend} on {device}, OpenClaw unavailable so copied to clipboard ({dispatch_reason})"
                    )
                else:
                    print(
                        f"Transcribed with {backend} on {device}, but OpenClaw output was empty ({dispatch_reason})"
                    )
                return

            if route == "typed":
                print(
                    f"Transcribed with {backend} on {device}, typed into focused input"
                )
            elif route == "pasted":
                print(
                    f"Transcribed with {backend} on {device}, pasted via system shortcut"
                )
            elif route == "clipboard":
                print(f"Transcribed with {backend} on {device}, copied to clipboard")
            else:
                print(f"Transcribed with {backend} on {device}, but output was empty")
        except Exception as error:
            print(f"Transcription failed: {error}")
        finally:
            self._safe_unlink(recording.path)
            with self._workers_lock:
                self._workers.discard(current)

    def _safe_unlink(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except Exception as error:
            print(f"Failed to remove temp audio file {path}: {error}")

    def _maybe_prewarm_transcriber(self) -> None:
        if not self._config.prewarm_on_start or self._prewarm_started:
            return
        self._prewarm_started = True

        worker = threading.Thread(
            target=self._prewarm_transcriber,
            args=(self._config.prewarm_delay_s,),
            daemon=True,
        )
        worker.start()

    def _prewarm_transcriber(self, delay_s: float = 0.0) -> None:
        if delay_s > 0:
            print(f"Transcriber prewarm scheduled in {delay_s:.1f}s")
            if self._stop_event.wait(timeout=delay_s):
                return

        try:
            self._transcriber.prewarm()
            print("Transcriber prewarm complete")
        except Exception as error:
            print(f"Transcriber prewarm skipped: {error}")

    def _set_recording_status(self, is_recording: bool) -> None:
        payload = {
            "recording": is_recording,
            "state": "recording" if is_recording else "idle",
        }
        path = self._config.status_file
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = tmp_path.write_text(json.dumps(payload), encoding="utf-8")
            _ = tmp_path.replace(path)
        except Exception:
            return
