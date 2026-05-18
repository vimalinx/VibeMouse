from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from vibemouse.core.commands import (
    COMMAND_RELOAD_CONFIG,
    COMMAND_SEND_ENTER,
    COMMAND_SHUTDOWN,
    EVENT_MOUSE_SIDE_FRONT_PRESS,
)
from vibemouse.core.backends.base import BackendUnavailableError
from vibemouse.app import VoiceMouseApp


class VoiceMouseAppWorkspaceTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> VoiceMouseApp:
        return object.__new__(VoiceMouseApp)

    def test_switch_workspace_left_uses_expected_dispatcher(self) -> None:
        subject = self._make_subject()
        switch = cast(Callable[[str], bool], getattr(subject, "_switch_workspace"))

        with patch(
            "vibemouse.app.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            ok = switch("left")

        self.assertTrue(ok)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["hyprctl", "dispatch", "workspace", "e-1"],
        )

    def test_switch_workspace_right_uses_expected_dispatcher(self) -> None:
        subject = self._make_subject()
        switch = cast(Callable[[str], bool], getattr(subject, "_switch_workspace"))

        with patch(
            "vibemouse.app.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            ok = switch("right")

        self.assertTrue(ok)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["hyprctl", "dispatch", "workspace", "e+1"],
        )

    def test_switch_workspace_returns_false_when_process_errors(self) -> None:
        subject = self._make_subject()
        switch = cast(Callable[[str], bool], getattr(subject, "_switch_workspace"))

        with patch(
            "vibemouse.app.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["hyprctl"], timeout=1.0),
        ):
            ok = switch("left")

        self.assertFalse(ok)

    def test_set_recording_status_writes_recording_payload(self) -> None:
        subject = self._make_subject()
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_file = Path(tmp) / "status.json"
            setattr(subject, "_config", SimpleNamespace(status_file=status_file))

            set_status = cast(
                Callable[[bool], None],
                getattr(subject, "_set_recording_status"),
            )
            set_status(True)

            payload = cast(
                dict[str, object],
                json.loads(status_file.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                payload,
                {"recording": True, "state": "recording", "listener_mode": "inline"},
            )

    def test_set_recording_status_writes_idle_payload(self) -> None:
        subject = self._make_subject()
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_file = Path(tmp) / "status.json"
            setattr(subject, "_config", SimpleNamespace(status_file=status_file))

            set_status = cast(
                Callable[[bool], None],
                getattr(subject, "_set_recording_status"),
            )
            set_status(False)

            payload = cast(
                dict[str, object],
                json.loads(status_file.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                payload,
                {"recording": False, "state": "idle", "listener_mode": "inline"},
            )

    def test_set_recording_status_includes_ipc_port_when_command_server_is_running(self) -> None:
        subject = self._make_subject()
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_file = Path(tmp) / "status.json"
            setattr(subject, "_config", SimpleNamespace(status_file=status_file))
            setattr(subject, "_command_server", SimpleNamespace(port=43125))

            set_status = cast(
                Callable[[bool], None],
                getattr(subject, "_set_recording_status"),
            )
            set_status(False)

            payload = cast(
                dict[str, object],
                json.loads(status_file.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                payload,
                {
                    "ipc_port": 43125,
                    "listener_mode": "inline",
                    "recording": False,
                    "state": "idle",
                },
            )


class VoiceMouseAppButtonBehaviorTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> VoiceMouseApp:
        return object.__new__(VoiceMouseApp)

    def test_front_press_stops_recording_with_default_output_target(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.1, path=Path("/tmp/voice.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )

        status_values: list[bool] = []
        worker_calls: list[tuple[object, str]] = []
        setattr(
            subject, "_set_recording_status", lambda value: status_values.append(value)
        )
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )

        on_front = cast(Callable[[], None], getattr(subject, "_on_front_press"))
        on_front()

        self.assertEqual(status_values, [False])
        self.assertEqual(worker_calls, [(recording, "default")])

    def test_rear_press_stops_recording_and_outputs_default_transcript(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.2, path=Path("/tmp/voice.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )

        status_values: list[bool] = []
        worker_calls: list[tuple[object, str]] = []
        send_enter_calls: list[str] = []
        setattr(
            subject, "_set_recording_status", lambda value: status_values.append(value)
        )
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )
        setattr(
            subject,
            "_output",
            SimpleNamespace(send_enter=lambda mode: send_enter_calls.append(mode)),
        )
        setattr(subject, "_config", SimpleNamespace(enter_mode="enter"))

        on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
        on_rear()

        self.assertEqual(status_values, [False])
        self.assertEqual(worker_calls, [(recording, "default")])
        self.assertEqual(send_enter_calls, [])

    def test_rear_press_sends_enter_when_idle(self) -> None:
        subject = self._make_subject()
        setattr(subject, "_recorder", SimpleNamespace(is_recording=False))
        send_enter_calls: list[str] = []
        setattr(
            subject,
            "_output",
            SimpleNamespace(send_enter=lambda mode: send_enter_calls.append(mode)),
        )
        setattr(subject, "_config", SimpleNamespace(enter_mode="ctrl_enter"))

        on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
        on_rear()

        self.assertEqual(send_enter_calls, ["ctrl_enter"])

    def test_rear_button_state_matrix(self) -> None:
        for is_recording in (True, False):
            with self.subTest(is_recording=is_recording):
                subject = self._make_subject()
                recording = SimpleNamespace(
                    duration_s=0.8, path=Path("/tmp/matrix.wav")
                )
                setattr(
                    subject,
                    "_recorder",
                    SimpleNamespace(
                        is_recording=is_recording,
                        stop_and_save=lambda: recording,
                    ),
                )
                setattr(subject, "_set_recording_status", lambda value: None)

                worker_calls: list[tuple[object, str]] = []
                send_enter_calls: list[str] = []
                setattr(
                    subject,
                    "_start_transcription_worker",
                    lambda rec, *, output_target: worker_calls.append(
                        (rec, output_target)
                    ),
                )
                setattr(
                    subject,
                    "_output",
                    SimpleNamespace(
                        send_enter=lambda mode: send_enter_calls.append(mode)
                    ),
                )
                setattr(subject, "_config", SimpleNamespace(enter_mode="enter"))

                on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
                on_rear()

                if is_recording:
                    self.assertEqual(worker_calls, [(recording, "default")])
                    self.assertEqual(send_enter_calls, [])
                else:
                    self.assertEqual(worker_calls, [])
                    self.assertEqual(send_enter_calls, ["enter"])

    def test_recording_submit_press_stops_recording_and_outputs_default_transcript(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=0.7, path=Path("/tmp/submit.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )
        setattr(subject, "_config", SimpleNamespace(enter_mode="enter"))

        status_values: list[bool] = []
        worker_calls: list[tuple[object, str]] = []
        send_enter_calls: list[str] = []
        setattr(
            subject, "_set_recording_status", lambda value: status_values.append(value)
        )
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )
        setattr(
            subject,
            "_output",
            SimpleNamespace(send_enter=lambda mode: send_enter_calls.append(mode)),
        )

        on_submit = cast(
            Callable[[], None], getattr(subject, "_on_recording_submit_press")
        )
        on_submit()

        self.assertEqual(status_values, [False])
        self.assertEqual(worker_calls, [(recording, "default")])
        self.assertEqual(send_enter_calls, [])

    def test_recording_submit_press_is_ignored_when_idle(self) -> None:
        subject = self._make_subject()
        setattr(subject, "_recorder", SimpleNamespace(is_recording=False))

        rear_calls: list[bool] = []
        setattr(subject, "_on_rear_press", lambda: rear_calls.append(True))

        on_submit = cast(
            Callable[[], None], getattr(subject, "_on_recording_submit_press")
        )
        on_submit()

        self.assertEqual(rear_calls, [])

    def test_handle_input_event_routes_through_binding_resolver(self) -> None:
        subject = self._make_subject()
        send_enter_calls: list[str] = []
        setattr(
            subject,
            "_binding_resolver",
            SimpleNamespace(
                resolve=lambda event_name: COMMAND_SEND_ENTER
                if event_name == EVENT_MOUSE_SIDE_FRONT_PRESS
                else None
            ),
        )
        setattr(
            subject,
            "_output",
            SimpleNamespace(send_enter=lambda mode: send_enter_calls.append(mode)),
        )
        setattr(subject, "_config", SimpleNamespace(enter_mode="enter"))

        handle_event = cast(
            Callable[[str], None],
            getattr(subject, "_handle_input_event"),
        )
        handle_event(EVENT_MOUSE_SIDE_FRONT_PRESS)

        self.assertEqual(send_enter_calls, ["enter"])

    def test_execute_command_reload_config_dispatches_to_reload_handler(self) -> None:
        subject = self._make_subject()
        reload_calls: list[bool] = []
        setattr(subject, "_command_lock", threading.RLock())
        setattr(subject, "_reload_config", lambda: reload_calls.append(True))

        execute_command = cast(
            Callable[[str], None],
            getattr(subject, "_execute_command"),
        )
        execute_command(COMMAND_RELOAD_CONFIG)

        self.assertEqual(reload_calls, [True])

    def test_execute_command_shutdown_sets_stop_event(self) -> None:
        subject = self._make_subject()
        stop_event = threading.Event()
        setattr(subject, "_command_lock", threading.RLock())
        setattr(subject, "_stop_event", stop_event)

        execute_command = cast(
            Callable[[str], None],
            getattr(subject, "_execute_command"),
        )
        execute_command(COMMAND_SHUTDOWN)

        self.assertTrue(stop_event.is_set())

    def test_transcribe_and_output_default_writes_processing_and_idle_status(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.0, path=Path("/tmp/transcribe.wav"))
        transcribe_calls: list[tuple[Path, str, list[tuple[str, int]]]] = []
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(
                transcribe=lambda path, *, output_target, hotwords: transcribe_calls.append(
                    (path, output_target, hotwords)
                )
                or "hello world",
                device_in_use="cpu",
                backend_in_use="funasr_enhanced",
            ),
        )
        setattr(
            subject,
            "_dictionary_service",
            SimpleNamespace(
                hotword_phrases=lambda scope: [("codex", 8)]
                if scope == "default"
                else [],
                normalize=lambda text, *, scope: "hello world",
            ),
        )

        inject_calls: list[tuple[str, bool]] = []
        toast_calls: list[str] = []
        readback_calls: list[str] = []
        setattr(
            subject,
            "_output",
            SimpleNamespace(
                inject_or_clipboard=lambda text, auto_paste: inject_calls.append(
                    (text, auto_paste)
                )
                or "typed",
            ),
        )
        setattr(subject, "_show_translation_toast", lambda text: toast_calls.append(text))
        setattr(subject, "_speak_readback", lambda text: readback_calls.append(text))
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_file = Path(tmp) / "status.json"
            setattr(
                subject,
                "_config",
                SimpleNamespace(auto_paste=True, status_file=status_file),
            )
            setattr(subject, "_listener_mode", "inline")
            setattr(subject, "_command_server", None)
            setattr(subject, "_recorder", SimpleNamespace(is_recording=False))
            setattr(subject, "_transcribe_lock", threading.Lock())
            setattr(subject, "_workers_lock", threading.Lock())
            setattr(subject, "_workers", set())

            removed_paths: list[Path] = []
            setattr(subject, "_safe_unlink", lambda path: removed_paths.append(path))

            transcribe_and_output = cast(
                Callable[[object, str], None],
                getattr(subject, "_transcribe_and_output"),
            )
            transcribe_and_output(recording, "default")

            payload = cast(
                dict[str, object],
                json.loads(status_file.read_text(encoding="utf-8")),
            )

        self.assertEqual(
            payload,
            {
                "last_transcript": "hello world",
                "listener_mode": "inline",
                "recording": False,
                "state": "idle",
            },
        )
        self.assertEqual(
            transcribe_calls,
            [(Path("/tmp/transcribe.wav"), "default", [("codex", 8)])],
        )
        self.assertEqual(toast_calls, ["hello world"])
        self.assertEqual(readback_calls, ["hello world"])
        self.assertEqual(inject_calls, [("hello world", True)])
        self.assertEqual(removed_paths, [Path("/tmp/transcribe.wav")])

    def test_transcribe_and_output_default_normalizes_text_before_local_output(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.0, path=Path("/tmp/default.wav"))
        transcribe_calls: list[tuple[Path, str, list[tuple[str, int]]]] = []
        normalize_calls: list[tuple[str, str]] = []
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(
                transcribe=lambda path, *, output_target, hotwords: transcribe_calls.append(
                    (path, output_target, hotwords)
                )
                or "please ask code x to review",
                device_in_use="cpu",
                backend_in_use="sensevoice_fast",
            ),
        )
        setattr(
            subject,
            "_dictionary_service",
            SimpleNamespace(
                hotword_phrases=lambda scope: [],
                normalize=lambda text, *, scope: normalize_calls.append((text, scope))
                or "please ask Codex to review",
            ),
        )

        inject_calls: list[tuple[str, bool]] = []
        toast_calls: list[str] = []
        readback_calls: list[str] = []
        setattr(
            subject,
            "_output",
            SimpleNamespace(
                inject_or_clipboard=lambda text, auto_paste: inject_calls.append(
                    (text, auto_paste)
                )
                or "typed",
            ),
        )
        setattr(subject, "_show_translation_toast", lambda text: toast_calls.append(text))
        setattr(subject, "_speak_readback", lambda text: readback_calls.append(text))
        setattr(subject, "_config", SimpleNamespace(auto_paste=True))
        setattr(subject, "_transcribe_lock", threading.Lock())
        setattr(subject, "_workers_lock", threading.Lock())
        setattr(subject, "_workers", set())
        setattr(subject, "_safe_unlink", lambda _path: None)

        transcribe_and_output = cast(
            Callable[[object, str], None],
            getattr(subject, "_transcribe_and_output"),
        )
        transcribe_and_output(recording, "default")

        self.assertEqual(
            transcribe_calls,
            [(Path("/tmp/default.wav"), "default", [])],
        )
        self.assertEqual(
            normalize_calls,
            [("please ask code x to review", "default")],
        )
        self.assertEqual(inject_calls, [("please ask Codex to review", True)])
        self.assertEqual(toast_calls, ["please ask Codex to review"])
        self.assertEqual(readback_calls, ["please ask Codex to review"])

    def test_show_translation_toast_is_disabled(self) -> None:
        subject = self._make_subject()
        setattr(subject, "_config", SimpleNamespace(translation_toast_enabled=True))

        with patch("vibemouse.app.translate_text_to_english") as translate_mock:
            show_translation_toast = cast(
                Callable[[str], None],
                getattr(subject, "_show_translation_toast"),
            )
            show_translation_toast("你好，世界。")

        translate_mock.assert_not_called()

    def test_speak_readback_uses_configured_speaker(self) -> None:
        subject = self._make_subject()
        calls: list[str] = []
        setattr(
            subject,
            "_config",
            SimpleNamespace(
                translation_provider="auto",
                translation_deepl_auth_key=None,
                translation_deepl_api_url=None,
                translation_libretranslate_url=None,
                translation_libretranslate_api_key=None,
                translation_mymemory_email=None,
                translation_mymemory_key=None,
            ),
        )
        setattr(subject, "_readback_tts", SimpleNamespace(speak_async=lambda text: calls.append(text)))

        speak_readback = cast(
            Callable[[str], None],
            getattr(subject, "_speak_readback"),
        )
        speak_readback("hello world")

        self.assertEqual(calls, [])

    def test_speak_readback_translates_chinese_before_speaking(self) -> None:
        subject = self._make_subject()
        calls: list[str] = []
        setattr(
            subject,
            "_config",
            SimpleNamespace(
                translation_provider="auto",
                translation_deepl_auth_key=None,
                translation_deepl_api_url=None,
                translation_libretranslate_url=None,
                translation_libretranslate_api_key=None,
                translation_mymemory_email=None,
                translation_mymemory_key=None,
            ),
        )
        setattr(subject, "_readback_tts", SimpleNamespace(speak_async=lambda text: calls.append(text)))

        with patch(
            "vibemouse.core.app.translate_text_to_english",
            return_value="Hello, world.",
        ) as translate_mock:
            speak_readback = cast(
                Callable[[str], None],
                getattr(subject, "_speak_readback"),
            )
            speak_readback("你好，世界。")

        translate_mock.assert_called_once()
        self.assertEqual(calls, ["Hello, world."])

    def test_transcribe_and_output_logs_explicit_backend_unavailable_error(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.0, path=Path("/tmp/fail.wav"))
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(
                transcribe=lambda _path, *, output_target, hotwords: (_ for _ in ()).throw(
                    BackendUnavailableError(
                        backend_id="funasr_enhanced",
                        reason="funasr package is not installed",
                    )
                )
            ),
        )
        setattr(
            subject,
            "_dictionary_service",
            SimpleNamespace(
                hotword_phrases=lambda scope: [("codex", 8)],
                normalize=lambda text, *, scope: text,
            ),
        )
        setattr(
            subject,
            "_output",
            SimpleNamespace(
                inject_or_clipboard=lambda _text, auto_paste: "typed",
            ),
        )
        setattr(subject, "_config", SimpleNamespace(auto_paste=False))
        setattr(subject, "_transcribe_lock", threading.Lock())
        setattr(subject, "_workers_lock", threading.Lock())
        setattr(subject, "_workers", set())
        setattr(subject, "_safe_unlink", lambda _path: None)

        transcribe_and_output = cast(
            Callable[[object, str], None],
            getattr(subject, "_transcribe_and_output"),
        )

        with self.assertLogs("vibemouse.core.app", level="ERROR") as captured:
            transcribe_and_output(recording, "default")

        self.assertTrue(
            any(
                "backend unavailable" in entry.lower()
                and "funasr package is not installed" in entry
                for entry in captured.output
            )
        )


class VoiceMouseAppPrewarmTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> VoiceMouseApp:
        return object.__new__(VoiceMouseApp)

    def test_maybe_prewarm_starts_worker_with_configured_delay(self) -> None:
        subject = self._make_subject()
        setattr(
            subject,
            "_config",
            SimpleNamespace(prewarm_on_start=True, prewarm_delay_s=2.5),
        )
        setattr(subject, "_prewarm_started", False)

        with patch("vibemouse.app.threading.Thread") as thread_cls:
            maybe_prewarm = cast(
                Callable[[], None],
                getattr(subject, "_maybe_prewarm_transcriber"),
            )
            maybe_prewarm()

        self.assertTrue(getattr(subject, "_prewarm_started"))
        thread_cls.assert_called_once()
        thread_kwargs = thread_cls.call_args.kwargs
        self.assertEqual(thread_kwargs["args"], (2.5,))
        self.assertTrue(thread_kwargs["daemon"])
        target = thread_kwargs["target"]
        self.assertIs(getattr(target, "__self__", None), subject)
        self.assertIs(
            getattr(target, "__func__", None),
            getattr(VoiceMouseApp, "_prewarm_transcriber"),
        )
        thread_cls.return_value.start.assert_called_once_with()

    def test_maybe_prewarm_skips_when_disabled(self) -> None:
        subject = self._make_subject()
        setattr(
            subject,
            "_config",
            SimpleNamespace(prewarm_on_start=False, prewarm_delay_s=2.0),
        )
        setattr(subject, "_prewarm_started", False)

        with patch("vibemouse.app.threading.Thread") as thread_cls:
            maybe_prewarm = cast(
                Callable[[], None],
                getattr(subject, "_maybe_prewarm_transcriber"),
            )
            maybe_prewarm()

        self.assertFalse(getattr(subject, "_prewarm_started"))
        thread_cls.assert_not_called()

    def test_maybe_prewarm_skips_when_already_started(self) -> None:
        subject = self._make_subject()
        setattr(
            subject,
            "_config",
            SimpleNamespace(prewarm_on_start=True, prewarm_delay_s=2.0),
        )
        setattr(subject, "_prewarm_started", True)

        with patch("vibemouse.app.threading.Thread") as thread_cls:
            maybe_prewarm = cast(
                Callable[[], None],
                getattr(subject, "_maybe_prewarm_transcriber"),
            )
            maybe_prewarm()

        thread_cls.assert_not_called()

    def test_prewarm_transcriber_waits_before_warmup(self) -> None:
        subject = self._make_subject()
        wait_calls: list[float] = []
        prewarm_calls: list[bool] = []
        setattr(
            subject,
            "_stop_event",
            SimpleNamespace(wait=lambda timeout: wait_calls.append(timeout) or False),
        )
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(prewarm=lambda: prewarm_calls.append(True)),
        )

        prewarm = cast(
            Callable[[float], None],
            getattr(subject, "_prewarm_transcriber"),
        )
        prewarm(1.5)

        self.assertEqual(wait_calls, [1.5])
        self.assertEqual(prewarm_calls, [True])

    def test_prewarm_transcriber_skips_when_stopped_during_delay(self) -> None:
        subject = self._make_subject()
        wait_calls: list[float] = []
        prewarm_calls: list[bool] = []
        setattr(
            subject,
            "_stop_event",
            SimpleNamespace(wait=lambda timeout: wait_calls.append(timeout) or True),
        )
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(prewarm=lambda: prewarm_calls.append(True)),
        )

        prewarm = cast(
            Callable[[float], None],
            getattr(subject, "_prewarm_transcriber"),
        )
        prewarm(2.0)

        self.assertEqual(wait_calls, [2.0])
        self.assertEqual(prewarm_calls, [])

    def test_prewarm_transcriber_without_delay_warms_immediately(self) -> None:
        subject = self._make_subject()
        prewarm_calls: list[bool] = []
        setattr(
            subject,
            "_stop_event",
            SimpleNamespace(
                wait=lambda timeout: (_ for _ in ()).throw(
                    AssertionError("wait should not be called when delay is zero")
                )
            ),
        )
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(prewarm=lambda: prewarm_calls.append(True)),
        )

        prewarm = cast(
            Callable[[float], None],
            getattr(subject, "_prewarm_transcriber"),
        )
        prewarm(0.0)

        self.assertEqual(prewarm_calls, [True])


class VoiceMouseAppLoggingTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> VoiceMouseApp:
        return object.__new__(VoiceMouseApp)

    def test_transcription_failure_logs_exception(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.0, path=Path("/tmp/fail.wav"))
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(
                transcribe=lambda _path, *, output_target, hotwords: (_ for _ in ()).throw(
                    RuntimeError("boom")
                )
            ),
        )
        setattr(
            subject,
            "_dictionary_service",
            SimpleNamespace(
                hotword_phrases=lambda scope: [],
                normalize=lambda text, *, scope: text,
            ),
        )
        setattr(
            subject,
            "_output",
            SimpleNamespace(
                inject_or_clipboard=lambda _text, auto_paste: "typed",
            ),
        )
        setattr(subject, "_config", SimpleNamespace(auto_paste=False))
        setattr(subject, "_transcribe_lock", threading.Lock())
        setattr(subject, "_workers_lock", threading.Lock())
        setattr(subject, "_workers", set())
        setattr(subject, "_safe_unlink", lambda _path: None)

        transcribe_and_output = cast(
            Callable[[object, str], None],
            getattr(subject, "_transcribe_and_output"),
        )

        with self.assertLogs("vibemouse.core.app", level="ERROR") as captured:
            transcribe_and_output(recording, "default")

        self.assertTrue(
            any("Transcription failed" in entry for entry in captured.output)
        )
