from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Literal

from vibemouse.bindings.actions import command_for_legacy_gesture_action
from vibemouse.bindings.resolver import BindingResolver
from vibemouse.core.audio import AudioRecorder, AudioRecording
from vibemouse.core.commands import (
    COMMAND_NOOP,
    COMMAND_RELOAD_CONFIG,
    COMMAND_SEND_ENTER,
    COMMAND_SHUTDOWN,
    COMMAND_SUBMIT_RECORDING,
    COMMAND_TOGGLE_RECORDING,
    COMMAND_TRIGGER_SECONDARY_ACTION,
    COMMAND_WORKSPACE_LEFT,
    COMMAND_WORKSPACE_RIGHT,
    EVENT_HOTKEY_RECORDING_SUBMIT,
    EVENT_HOTKEY_RECORD_TOGGLE,
    gesture_direction_to_event,
)
from vibemouse.config import AppConfig, load_config, write_status
from vibemouse.core.output import TextOutput
from vibemouse.core.transcriber import SenseVoiceTranscriber
from vibemouse.ipc.server import AgentCommandServer, IPCServer
from vibemouse.listener.keyboard_listener import KeyboardHotkeyListener
from vibemouse.listener.mouse_listener import SideButtonListener
from vibemouse.platform.system_integration import (
    SystemIntegration,
    create_system_integration,
)


ListenerMode = Literal["inline", "child", "off"]
TranscriptionTarget = Literal["default", "openclaw"]
_LOG = logging.getLogger(__name__)


class VoiceMouseApp:
    def __init__(
        self,
        config: AppConfig,
        *,
        listener_mode: ListenerMode = "inline",
        config_path: Path | str | None = None,
    ) -> None:
        if config.front_button == config.rear_button:
            raise ValueError("Front and rear side buttons must be different")

        self._config: AppConfig = config
        self._listener_mode: ListenerMode = listener_mode
        self._config_path: Path | None = Path(config_path) if config_path else None
        self._system_integration: SystemIntegration = create_system_integration()
        self._listener: SideButtonListener | None = None
        self._keyboard_listener: KeyboardHotkeyListener | None = None
        self._recording_submit_listener: KeyboardHotkeyListener | None = None
        self._ipc_server: IPCServer | None = None
        self._listener_process: subprocess.Popen | None = None
        self._command_server: AgentCommandServer | None = None

        self._stop_event: threading.Event = threading.Event()
        self._transcribe_lock: threading.Lock = threading.Lock()
        self._workers_lock: threading.Lock = threading.Lock()
        self._workers: set[threading.Thread] = set()
        self._prewarm_started: bool = False
        self._command_lock: threading.RLock = threading.RLock()
        self._configure_runtime(config)

    def run(self) -> None:
        self._start_command_server()
        self._start_listener_mode()
        self._set_recording_status(False, listener_mode=self._listener_mode)
        recording_submit_hotkey = self._config.recording_submit_keycode
        _LOG.info(
            "VibeMouse ready. "
            + f"Model={self._config.model_name}, preferred_device={self._config.device}, "
            + f"backend={self._config.transcriber_backend}, auto_paste={self._config.auto_paste}, "
            + f"enter_mode={self._config.enter_mode}, debounce_ms={self._config.button_debounce_ms}, "
            + f"front_button={self._config.front_button}, rear_button={self._config.rear_button}, "
            + f"record_hotkey_keycodes={self._config.record_hotkey_keycodes}, "
            + f"recording_submit_keycode={recording_submit_hotkey}, "
            + f"gestures_enabled={self._config.gestures_enabled}, "
            + f"gesture_trigger={self._config.gesture_trigger_button}, "
            + f"gesture_threshold_px={self._config.gesture_threshold_px}, "
            + f"gesture_freeze_pointer={self._config.gesture_freeze_pointer}, "
            + f"gesture_restore_cursor={self._config.gesture_restore_cursor}, "
            + f"prewarm_on_start={self._config.prewarm_on_start}, "
            + f"prewarm_delay_s={self._config.prewarm_delay_s}, "
            + f"listener_mode={self._listener_mode}. "
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
        self._stop_listener_mode()
        if self._command_server is not None:
            self._command_server.stop()
            self._command_server = None
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
            _LOG.warning(
                f"Shutdown warning: {len(still_running)} transcription worker(s) are still running"
            )

    def _on_front_press(self) -> None:
        self._execute_command(COMMAND_TOGGLE_RECORDING)

    def _on_rear_press(self) -> None:
        self._execute_command(COMMAND_TRIGGER_SECONDARY_ACTION)

    def _on_recording_submit_press(self) -> None:
        self._execute_command(COMMAND_SUBMIT_RECORDING)

    def _on_gesture(self, direction: str) -> None:
        event_name = gesture_direction_to_event(direction)
        if event_name is None:
            _LOG.warning("Gesture '%s' mapped to unknown direction", direction)
            return

        try:
            binding_resolver = self._binding_resolver
        except AttributeError:
            action = self._resolve_gesture_action(direction)
            self._execute_command(command_for_legacy_gesture_action(action))
            return

        command_name = binding_resolver.resolve(event_name)
        if command_name is None:
            _LOG.info("Gesture '%s' recognized with no action configured", direction)
            return
        self._execute_command(command_name, source_event=event_name)

    def _handle_input_event(self, event_name: str) -> None:
        command_name = self._binding_resolver.resolve(event_name)
        if command_name is None:
            _LOG.debug("Ignoring unbound input event: %s", event_name)
            return
        self._execute_command(command_name, source_event=event_name)

    def _execute_command(
        self,
        command_name: str,
        *,
        source_event: str | None = None,
    ) -> None:
        command_lock = getattr(self, "_command_lock", None)
        if command_lock is None:
            self._execute_command_unlocked(command_name, source_event=source_event)
            return
        with command_lock:
            self._execute_command_unlocked(command_name, source_event=source_event)

    def _execute_command_unlocked(
        self,
        command_name: str,
        *,
        source_event: str | None = None,
    ) -> None:
        if source_event is not None:
            _LOG.debug("Resolved input event '%s' -> '%s'", source_event, command_name)

        if command_name == COMMAND_NOOP:
            if source_event is not None:
                _LOG.info("Input event '%s' resolved to noop", source_event)
            return
        if command_name == COMMAND_TOGGLE_RECORDING:
            self._toggle_recording()
            return
        if command_name == COMMAND_TRIGGER_SECONDARY_ACTION:
            self._trigger_secondary_action()
            return
        if command_name == COMMAND_SUBMIT_RECORDING:
            self._submit_recording()
            return
        if command_name == COMMAND_SEND_ENTER:
            self._send_enter_command(force_when_disabled=True)
            return
        if command_name == COMMAND_WORKSPACE_LEFT:
            self._dispatch_workspace_command("left")
            return
        if command_name == COMMAND_WORKSPACE_RIGHT:
            self._dispatch_workspace_command("right")
            return
        if command_name == COMMAND_RELOAD_CONFIG:
            self._reload_config()
            return
        if command_name == COMMAND_SHUTDOWN:
            self._request_shutdown()
            return

        _LOG.warning("Ignoring unsupported command '%s'", command_name)

    def _toggle_recording(self) -> None:
        if not self._recorder.is_recording:
            try:
                self._recorder.start()
                self._set_recording_status(True)
                _LOG.info("Recording started")
            except Exception as error:
                self._set_recording_status(False)
                _LOG.exception("Failed to start recording: %s", error)
            return

        try:
            recording = self._stop_recording()
        except Exception as error:
            _LOG.exception("Failed to stop recording: %s", error)
            return

        if recording is None:
            return

        self._start_transcription_worker(recording, output_target="default")

    def _trigger_secondary_action(self) -> None:
        if self._recorder.is_recording:
            self._stop_recording_for_output(
                output_target="openclaw",
                error_prefix="Failed to stop recording from secondary action",
                success_message=(
                    "Recording stopped by secondary action, sending transcript to OpenClaw"
                ),
            )
            return

        self._send_enter_command(force_when_disabled=False)

    def _submit_recording(self) -> None:
        if not self._recorder.is_recording:
            return

        self._stop_recording_for_output(
            output_target="openclaw",
            error_prefix="Failed to stop recording from submit command",
            success_message="Recording submit command received, sending transcript to OpenClaw",
        )

    def _send_enter_command(self, *, force_when_disabled: bool) -> None:
        try:
            mode = self._config.enter_mode
            if force_when_disabled and mode == "none":
                mode = "enter"
            self._output.send_enter(mode=mode)
            if mode == "none":
                _LOG.info("Enter key handling disabled (enter_mode=none)")
            else:
                _LOG.info("Enter key sent")
        except Exception as error:
            _LOG.exception("Failed to send Enter: %s", error)

    def _resolve_gesture_action(self, direction: str) -> str:
        mapping = {
            "up": self._config.gesture_up_action,
            "down": self._config.gesture_down_action,
            "left": self._config.gesture_left_action,
            "right": self._config.gesture_right_action,
        }
        return mapping.get(direction, "noop")

    def _dispatch_workspace_command(self, direction: str) -> None:
        if self._switch_workspace(direction):
            _LOG.info("Workspace switch command succeeded: %s", direction)
            return
        _LOG.warning("Workspace switch command failed: %s", direction)

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
            _LOG.info("Recording was empty and has been discarded")
            return None
        return recording

    def _stop_recording_for_output(
        self,
        *,
        output_target: TranscriptionTarget,
        error_prefix: str,
        success_message: str | None = None,
    ) -> None:
        try:
            recording = self._stop_recording()
        except Exception as error:
            _LOG.exception("%s: %s", error_prefix, error)
            return

        if recording is None:
            return

        if success_message is not None:
            _LOG.info(success_message)
        self._start_transcription_worker(recording, output_target=output_target)

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
            _LOG.info(
                "Recording stopped (%.1fs), transcribing...", recording.duration_s
            )
            with self._transcribe_lock:
                text = self._transcriber.transcribe(recording.path)

            if not text:
                _LOG.info("No speech recognized")
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
                    _LOG.info(
                        "Transcribed with %s on %s, sent to OpenClaw (%s)",
                        backend,
                        device,
                        dispatch_reason,
                    )
                elif route == "clipboard":
                    _LOG.warning(
                        "Transcribed with %s on %s, OpenClaw unavailable so copied to clipboard (%s)",
                        backend,
                        device,
                        dispatch_reason,
                    )
                else:
                    _LOG.warning(
                        "Transcribed with %s on %s, but OpenClaw output was empty (%s)",
                        backend,
                        device,
                        dispatch_reason,
                    )
                return

            if route == "typed":
                _LOG.info(
                    "Transcribed with %s on %s, typed into focused input",
                    backend,
                    device,
                )
            elif route == "pasted":
                _LOG.info(
                    "Transcribed with %s on %s, pasted via system shortcut",
                    backend,
                    device,
                )
            elif route == "clipboard":
                _LOG.info(
                    "Transcribed with %s on %s, copied to clipboard", backend, device
                )
            else:
                _LOG.warning(
                    "Transcribed with %s on %s, but output was empty", backend, device
                )
        except Exception as error:
            _LOG.exception("Transcription failed: %s", error)
        finally:
            self._safe_unlink(recording.path)
            with self._workers_lock:
                self._workers.discard(current)

    def _safe_unlink(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except Exception as error:
            _LOG.warning("Failed to remove temp audio file %s: %s", path, error)

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
            _LOG.info("Transcriber prewarm scheduled in %.1fs", delay_s)
            if self._stop_event.wait(timeout=delay_s):
                return

        try:
            self._transcriber.prewarm()
            _LOG.info("Transcriber prewarm complete")
        except Exception as error:
            _LOG.warning("Transcriber prewarm skipped: %s", error)

    def _start_listener_child(self) -> None:
        """Spawn listener as subprocess and start IPC server to receive events."""
        cmd = [
            sys.executable,
            "-m",
            "vibemouse.cli.main",
            "listener",
            "run",
            "--connect",
            "stdio",
        ]
        if self._config_path is not None:
            cmd.extend(["--config", str(self._config_path)])
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._listener_process = proc
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("Failed to create listener subprocess pipes")
        self._ipc_server = IPCServer(
            reader=proc.stdout,
            writer=proc.stdin,
            on_event=self._handle_input_event,
        )
        self._ipc_server.start()
        _LOG.info("Listener child process started (listener_mode=child)")

    def _configure_runtime(self, config: AppConfig) -> None:
        self._config = config
        self._binding_resolver = BindingResolver.from_config(config)
        self._recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            dtype=config.dtype,
            temp_dir=config.temp_dir,
        )
        self._transcriber = SenseVoiceTranscriber(config)
        self._output = TextOutput(
            system_integration=self._system_integration,
            openclaw_command=config.openclaw_command,
            openclaw_agent=config.openclaw_agent,
            openclaw_timeout_s=config.openclaw_timeout_s,
            openclaw_retries=config.openclaw_retries,
        )
        self._listener = None
        self._keyboard_listener = None
        self._recording_submit_listener = None
        if self._listener_mode == "inline":
            self._listener = SideButtonListener(
                on_event=self._handle_input_event,
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
            self._keyboard_listener = KeyboardHotkeyListener(
                on_event=self._handle_input_event,
                event_name=EVENT_HOTKEY_RECORD_TOGGLE,
                keycodes=config.record_hotkey_keycodes,
                debounce_s=config.button_debounce_ms / 1000.0,
            )
            if config.recording_submit_keycode is not None:
                self._recording_submit_listener = KeyboardHotkeyListener(
                    on_event=self._handle_input_event,
                    event_name=EVENT_HOTKEY_RECORDING_SUBMIT,
                    keycodes=(config.recording_submit_keycode,),
                    debounce_s=config.button_debounce_ms / 1000.0,
                )

    def _start_command_server(self) -> None:
        if self._command_server is not None:
            return
        self._command_server = AgentCommandServer(on_command=self._execute_command)
        self._command_server.start()
        _LOG.info("Agent command server listening on 127.0.0.1:%s", self._command_server.port)

    def _start_listener_mode(self) -> None:
        if self._listener_mode == "child":
            self._start_listener_child()
            return
        if self._listener_mode == "inline":
            assert self._listener is not None and self._keyboard_listener is not None
            self._listener.start()
            self._keyboard_listener.start()
            if self._recording_submit_listener is not None:
                self._recording_submit_listener.start()

    def _stop_listener_mode(self) -> None:
        if self._ipc_server is not None:
            self._ipc_server.send_command(COMMAND_SHUTDOWN)
            self._ipc_server.stop()
            self._ipc_server = None
        if self._listener_process is not None:
            try:
                self._listener_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._listener_process.kill()
            self._listener_process = None
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        if self._recording_submit_listener is not None:
            self._recording_submit_listener.stop()
            self._recording_submit_listener = None

    def _reload_config(self) -> None:
        if self._recorder.is_recording:
            _LOG.warning("Ignoring reload_config while recording is active")
            return
        with self._workers_lock:
            if self._workers:
                _LOG.warning("Ignoring reload_config while transcription workers are still running")
                return
        config_path = self._config_path
        if config_path is None:
            _LOG.warning("Ignoring reload_config because no config path is available")
            return
        try:
            config = load_config(config_path)
        except Exception as error:
            _LOG.exception("Failed to reload config from %s: %s", config_path, error)
            return
        self._stop_listener_mode()
        self._configure_runtime(config)
        self._start_listener_mode()
        self._set_recording_status(False, listener_mode=self._listener_mode)
        _LOG.info("Config reloaded from %s", config_path)

    def _request_shutdown(self) -> None:
        _LOG.info("Shutdown command received")
        self._stop_event.set()

    def _set_recording_status(
        self,
        is_recording: bool,
        *,
        listener_mode: ListenerMode | None = None,
    ) -> None:
        mode = (
            listener_mode
            if listener_mode is not None
            else getattr(self, "_listener_mode", "inline")
        )
        payload: dict[str, object] = {
            "recording": is_recording,
            "state": "recording" if is_recording else "idle",
            "listener_mode": mode,
        }
        command_server = getattr(self, "_command_server", None)
        if command_server is not None and getattr(command_server, "port", 0):
            payload["ipc_port"] = int(command_server.port)
        try:
            write_status(self._config.status_file, payload)
        except Exception:
            return
