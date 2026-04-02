"""CLI entry point for standalone listener process (IPC client mode)."""

from __future__ import annotations

import argparse
import sys

from vibemouse.config import load_config
from vibemouse.core.commands import (
    EVENT_HOTKEY_RECORDING_SUBMIT,
    EVENT_HOTKEY_RECORD_TOGGLE,
)
from vibemouse.core.logging_setup import configure_logging
from vibemouse.ipc.client import IPCClient
from vibemouse.listener.keyboard_listener import KeyboardHotkeyListener
from vibemouse.listener.mouse_listener import SideButtonListener
from vibemouse.platform.system_integration import create_system_integration


def run_listener_connect_stdio(config_path: str | None = None) -> int:
    """
    Run listener as standalone process, sending events via stdio (LPJSON).
    Used when agent spawns listener with --listener=child.
    """
    config = load_config(config_path)
    configure_logging(config.log_level)

    client = IPCClient(
        stdin=sys.stdin,
        stdout=sys.stdout,
        on_command=lambda cmd: _handle_command(client, cmd),
    )

    system_integration = create_system_integration()
    mouse_listener = SideButtonListener(
        on_event=client.send_event,
        front_button=config.front_button,
        rear_button=config.rear_button,
        debounce_s=config.button_debounce_ms / 1000.0,
        gestures_enabled=config.gestures_enabled,
        gesture_trigger_button=config.gesture_trigger_button,
        gesture_threshold_px=config.gesture_threshold_px,
        gesture_freeze_pointer=config.gesture_freeze_pointer,
        gesture_restore_cursor=config.gesture_restore_cursor,
        system_integration=system_integration,
    )
    keyboard_listener = KeyboardHotkeyListener(
        on_event=client.send_event,
        event_name=EVENT_HOTKEY_RECORD_TOGGLE,
        keycodes=config.record_hotkey_keycodes,
        debounce_s=config.button_debounce_ms / 1000.0,
    )
    recording_submit_listener: KeyboardHotkeyListener | None = None
    if config.recording_submit_keycode is not None:
        recording_submit_listener = KeyboardHotkeyListener(
            on_event=client.send_event,
            event_name=EVENT_HOTKEY_RECORDING_SUBMIT,
            keycodes=(config.recording_submit_keycode,),
            debounce_s=config.button_debounce_ms / 1000.0,
        )

    mouse_listener.start()
    keyboard_listener.start()
    if recording_submit_listener is not None:
        recording_submit_listener.start()

    try:
        client.run()
    finally:
        client.stop()
        mouse_listener.stop()
        keyboard_listener.stop()
        if recording_submit_listener is not None:
            recording_submit_listener.stop()

    return 0


def _handle_command(client: IPCClient, command: str) -> None:
    if command == "shutdown":
        client.stop()
        try:
            sys.stdin.close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vibemouse listener")
    subparsers = parser.add_subparsers(dest="subcommand")
    run_parser = subparsers.add_parser("run", help="run listener process")
    run_parser.add_argument(
        "--connect",
        required=True,
        choices=["stdio"],
        help="IPC transport (stdio = LPJSON over stdin/stdout)",
    )
    run_parser.add_argument(
        "--config",
        default=None,
        help="path to config.json",
    )
    args = parser.parse_args(argv)

    if args.subcommand != "run":
        parser.print_help()
        return 1
    if getattr(args, "connect", None) != "stdio":
        run_parser.error("--connect stdio is required for listener run")
        return 1

    return run_listener_connect_stdio(config_path=getattr(args, "config", None))
