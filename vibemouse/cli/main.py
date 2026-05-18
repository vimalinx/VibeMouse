from __future__ import annotations

import argparse
import webbrowser

from vibemouse.config import load_config
from vibemouse.config.store import resolve_config_path
from vibemouse.core.app import VoiceMouseApp
from vibemouse.core.logging_setup import configure_logging
from vibemouse.ops.deploy import configure_deploy_parser, run_deploy
from vibemouse.ops.doctor import run_doctor
from vibemouse.ops.smoke import run_smoke
from vibemouse.settings import SettingsServer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vibemouse")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="run the voice-input daemon (alias for agent run --listener=inline)")
    run_parser.add_argument("--config", default=None, help="path to config.json")

    agent_parser = subparsers.add_parser("agent", help="agent subcommands")
    agent_sub = agent_parser.add_subparsers(dest="agent_command")
    agent_run = agent_sub.add_parser("run", help="run the agent")
    agent_run.add_argument(
        "--listener",
        choices=["inline", "child", "off"],
        default="inline",
        help="listener mode: inline (in-process), child (subprocess via IPC), off (no listener)",
    )
    agent_run.add_argument("--config", default=None, help="path to config.json")

    listener_parser = subparsers.add_parser("listener", help="listener subcommands")
    listener_sub = listener_parser.add_subparsers(dest="listener_command")
    listener_run = listener_sub.add_parser("run", help="run listener process (for --connect stdio)")
    listener_run.add_argument(
        "--connect",
        required=True,
        choices=["stdio"],
        help="IPC transport (stdio = LPJSON over stdin/stdout)",
    )
    listener_run.add_argument("--config", default=None, help="path to config.json")

    doctor_parser = subparsers.add_parser("doctor", help="run environment diagnostics")
    doctor_parser.add_argument(
        "--fix",
        action="store_true",
        help="apply safe auto-remediations before running checks",
    )
    smoke_parser = subparsers.add_parser(
        "smoke",
        help="run software integration smoke checks",
    )
    smoke_parser.add_argument("--config", default=None, help="path to config.json")

    deploy_parser = subparsers.add_parser(
        "deploy",
        help="generate service/env files and deploy as user service",
    )
    configure_deploy_parser(deploy_parser)

    settings_parser = subparsers.add_parser(
        "settings",
        help="run the local settings web UI",
    )
    settings_parser.add_argument("--config", default=None, help="path to config.json")
    settings_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host interface for the local settings server",
    )
    settings_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="port for the local settings server",
    )
    settings_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="open the settings page in the default browser",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    raw_command = getattr(args, "command", None)
    command = raw_command if isinstance(raw_command, str) else "run"

    if command == "doctor":
        apply_fixes_raw = getattr(args, "fix", False)
        apply_fixes = bool(apply_fixes_raw)
        return run_doctor(apply_fixes=apply_fixes)
    if command == "smoke":
        return run_smoke(args)
    if command == "deploy":
        return run_deploy(args)
    if command == "settings":
        resolved_path = resolve_config_path(getattr(args, "config", None))
        configure_logging("INFO")
        server = SettingsServer(
            config_path=resolved_path,
            host=getattr(args, "host", "127.0.0.1"),
            port=int(getattr(args, "port", 8765)),
        )
        server.start()
        if bool(getattr(args, "open_browser", False)):
            webbrowser.open(f"{server.base_url}/", new=2)
        try:
            server.wait()
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
        return 0

    if command == "listener":
        listener_cmd = getattr(args, "listener_command", None)
        if listener_cmd != "run":
            parser.parse_args([*((argv or [])[:0]), "listener", "--help"])
            return 1
        from vibemouse.cli.listener_cli import run_listener_connect_stdio
        return run_listener_connect_stdio(config_path=getattr(args, "config", None))

    if command == "agent":
        agent_cmd = getattr(args, "agent_command", None)
        if agent_cmd != "run":
            parser.parse_args([*((argv or [])[:0]), "agent", "--help"])
            return 1
        listener_mode = getattr(args, "listener", "inline")
    else:
        # "run" - legacy alias for agent run --listener=inline
        listener_mode = "inline"
    config_path = getattr(args, "config", None)

    config = load_config(config_path)
    configure_logging(config.log_level)
    resolved_path = resolve_config_path(config_path)
    app = VoiceMouseApp(
        config,
        listener_mode=listener_mode,
        config_path=resolved_path,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
