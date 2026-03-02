from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from vibemouse.doctor import run_doctor


_PRESET_OVERRIDES: dict[str, dict[str, str]] = {
    "stable": {
        "VIBEMOUSE_AUTO_PASTE": "true",
        "VIBEMOUSE_BUTTON_DEBOUNCE_MS": "220",
        "VIBEMOUSE_PREWARM_ON_START": "true",
        "VIBEMOUSE_OPENCLAW_RETRIES": "1",
    },
    "fast": {
        "VIBEMOUSE_AUTO_PASTE": "true",
        "VIBEMOUSE_BUTTON_DEBOUNCE_MS": "120",
        "VIBEMOUSE_PREWARM_ON_START": "true",
        "VIBEMOUSE_OPENCLAW_RETRIES": "2",
    },
    "low-resource": {
        "VIBEMOUSE_AUTO_PASTE": "false",
        "VIBEMOUSE_BUTTON_DEBOUNCE_MS": "250",
        "VIBEMOUSE_PREWARM_ON_START": "false",
        "VIBEMOUSE_OPENCLAW_RETRIES": "0",
    },
}


def configure_deploy_parser(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--preset",
        choices=sorted(_PRESET_OVERRIDES.keys()),
        default="stable",
        help="deployment preset profile",
    )
    _ = parser.add_argument(
        "--env-file",
        default=str(Path.home() / ".config" / "vibemouse" / "deploy.env"),
        help="path to generated EnvironmentFile",
    )
    _ = parser.add_argument(
        "--service-file",
        default=str(Path.home() / ".config" / "systemd" / "user" / "vibemouse.service"),
        help="path to generated systemd user service file",
    )
    _ = parser.add_argument(
        "--openclaw-command",
        default=shutil.which("openclaw") or "openclaw",
        help="OpenClaw command prefix",
    )
    _ = parser.add_argument(
        "--openclaw-agent",
        default="main",
        help="OpenClaw agent id used for rear-button routing",
    )
    _ = parser.add_argument(
        "--openclaw-retries",
        type=int,
        default=None,
        help="override retries for OpenClaw spawn failures",
    )
    _ = parser.add_argument(
        "--exec-start",
        default=None,
        help="override ExecStart command",
    )
    _ = parser.add_argument(
        "--skip-systemctl",
        action="store_true",
        help="skip systemctl enable/restart operations",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print plan without writing files",
    )


def run_deploy(args: argparse.Namespace) -> int:
    preset = str(getattr(args, "preset", "stable"))
    if preset not in _PRESET_OVERRIDES:
        print(f"Unknown preset: {preset}")
        return 1

    openclaw_command = str(getattr(args, "openclaw_command", "openclaw")).strip()
    if not openclaw_command:
        print("--openclaw-command must not be empty")
        return 1

    openclaw_agent = str(getattr(args, "openclaw_agent", "main")).strip() or "main"

    retries_override = cast(int | None, getattr(args, "openclaw_retries", None))

    if retries_override is not None and retries_override < 0:
        print("--openclaw-retries must be non-negative")
        return 1

    env_path = Path(str(getattr(args, "env_file", ""))).expanduser()
    service_path = Path(str(getattr(args, "service_file", ""))).expanduser()
    exec_start = _resolve_exec_start(str(getattr(args, "exec_start", "") or ""))

    env_map = build_deploy_env(
        preset=preset,
        openclaw_command=openclaw_command,
        openclaw_agent=openclaw_agent,
        openclaw_retries=retries_override,
    )
    env_content = render_env_file(env_map)
    service_content = render_service_file(
        env_file=env_path,
        exec_start=exec_start,
    )

    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run:
        print(f"[DRY-RUN] would write {env_path}")
        print(f"[DRY-RUN] would write {service_path}")
        print(f"[DRY-RUN] preset={preset}")
        print(f"[DRY-RUN] exec_start={exec_start}")
        return 0

    _write_text(env_path, env_content)
    _write_text(service_path, service_content)
    print(f"Wrote {env_path}")
    print(f"Wrote {service_path}")

    if not bool(getattr(args, "skip_systemctl", False)):
        service_name = service_path.name
        if not _run_systemctl(["daemon-reload"]):
            return 1
        if not _run_systemctl(["enable", "--now", service_name]):
            return 1
        if not _run_systemctl(["is-active", service_name]):
            return 1

    print("Running doctor checks...")
    return run_doctor()


def build_deploy_env(
    *,
    preset: str,
    openclaw_command: str,
    openclaw_agent: str,
    openclaw_retries: int | None,
) -> dict[str, str]:
    base = {
        "VIBEMOUSE_BACKEND": "auto",
        "VIBEMOUSE_DEVICE": "cpu",
        "VIBEMOUSE_FALLBACK_CPU": "true",
        "VIBEMOUSE_ENTER_MODE": "enter",
        "VIBEMOUSE_OPENCLAW_COMMAND": openclaw_command,
        "VIBEMOUSE_OPENCLAW_AGENT": openclaw_agent,
        "VIBEMOUSE_OPENCLAW_TIMEOUT_S": "20.0",
        "VIBEMOUSE_STATUS_FILE": "%t/vibemouse-status.json",
    }
    base.update(_PRESET_OVERRIDES[preset])
    if openclaw_retries is not None:
        base["VIBEMOUSE_OPENCLAW_RETRIES"] = str(openclaw_retries)
    return base


def render_env_file(env_map: dict[str, str]) -> str:
    lines = [
        "# Generated by `vibemouse deploy`.",
        "# Edit values if needed, then: systemctl --user restart vibemouse.service",
    ]
    for key in sorted(env_map.keys()):
        lines.append(f"{key}={_quote_env_value(env_map[key])}")
    lines.append("")
    return "\n".join(lines)


def render_service_file(*, env_file: Path, exec_start: str) -> str:
    lines = [
        "[Unit]",
        "Description=VibeMouse voice input service",
        "After=graphical-session.target",
        "PartOf=graphical-session.target",
        "",
        "[Service]",
        "Type=simple",
        f"EnvironmentFile={env_file}",
        f"ExecStart={exec_start}",
        "Restart=on-failure",
        "RestartSec=2",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ]
    return "\n".join(lines)


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _resolve_exec_start(raw_exec_start: str) -> str:
    cleaned = raw_exec_start.strip()
    if cleaned:
        return cleaned

    python_bin = sys.executable
    return f"{python_bin} -m vibemouse.main run"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _run_systemctl(args: list[str]) -> bool:
    cmd = ["systemctl", "--user", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=12.0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Failed to run {' '.join(cmd)}: {error}")
        return False

    if proc.returncode == 0:
        return True

    stderr = proc.stderr.strip()
    if stderr:
        print(f"systemctl {' '.join(args)} failed: {stderr}")
    else:
        print(f"systemctl {' '.join(args)} failed with code {proc.returncode}")
    return False


def validate_openclaw_command(raw: str) -> bool:
    try:
        parts = shlex.split(raw)
    except ValueError:
        return False
    return bool(parts)
