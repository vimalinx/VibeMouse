from __future__ import annotations

import importlib
import json
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from vibemouse.config import AppConfig, load_config


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def run_doctor() -> int:
    checks: list[DoctorCheck] = []

    config_check, config = _check_config_load()
    checks.append(config_check)

    if config is not None:
        checks.extend(_check_openclaw(config))

    checks.append(_check_audio_input(config))
    checks.append(_check_input_device_permissions(config))

    checks.append(_check_hyprland_return_bind_conflict(config))
    checks.append(_check_user_service_state())

    _print_checks(checks)

    fail_count = sum(1 for check in checks if check.status == "fail")
    warn_count = sum(1 for check in checks if check.status == "warn")
    print(f"Doctor summary: {len(checks)} checks, {fail_count} fail, {warn_count} warn")
    return 1 if fail_count else 0


def _check_config_load() -> tuple[DoctorCheck, AppConfig | None]:
    try:
        config = load_config()
    except Exception as error:
        return (
            DoctorCheck(
                name="config",
                status="fail",
                detail=f"failed to load config: {error}",
            ),
            None,
        )

    return (
        DoctorCheck(
            name="config",
            status="ok",
            detail=(
                "loaded "
                + f"front={config.front_button}, rear={config.rear_button}, "
                + f"openclaw_agent={config.openclaw_agent or 'none'}"
            ),
        ),
        config,
    )


def _check_openclaw(config: AppConfig) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    command_parts = _parse_openclaw_command(config.openclaw_command)
    if command_parts is None:
        checks.append(
            DoctorCheck(
                name="openclaw-command",
                status="fail",
                detail="invalid VIBEMOUSE_OPENCLAW_COMMAND shell syntax",
            )
        )
        return checks

    executable = command_parts[0]
    resolved = shutil.which(executable)
    if resolved is None:
        checks.append(
            DoctorCheck(
                name="openclaw-command",
                status="fail",
                detail=f"executable not found in PATH: {executable}",
            )
        )
        return checks

    checks.append(
        DoctorCheck(
            name="openclaw-command",
            status="ok",
            detail=f"resolved executable: {resolved}",
        )
    )

    configured_agent = config.openclaw_agent
    if not configured_agent:
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail="no agent configured; set VIBEMOUSE_OPENCLAW_AGENT",
            )
        )
        return checks

    probe_cmd = [*command_parts, "agents", "list", "--json"]
    try:
        probe = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=8.0,
        )
    except subprocess.TimeoutExpired:
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail="timed out while probing available agents",
            )
        )
        return checks
    except OSError as error:
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail=f"failed to run agent probe: {error}",
            )
        )
        return checks

    if probe.returncode != 0:
        stderr = probe.stderr.strip()
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail=(
                    "agent probe failed"
                    if not stderr
                    else f"agent probe failed: {stderr}"
                ),
            )
        )
        return checks

    try:
        payload = json.loads(probe.stdout)
    except json.JSONDecodeError:
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail="agent probe returned invalid JSON",
            )
        )
        return checks

    if not isinstance(payload, list):
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail="agent probe returned unexpected payload shape",
            )
        )
        return checks

    available_agents = {
        str(entry.get("id", "")).strip() for entry in payload if isinstance(entry, dict)
    }
    if configured_agent in available_agents:
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="ok",
                detail=f"configured agent exists: {configured_agent}",
            )
        )
    else:
        sample = ", ".join(sorted(agent for agent in available_agents if agent)[:5])
        checks.append(
            DoctorCheck(
                name="openclaw-agent",
                status="warn",
                detail=(
                    f"configured agent not found: {configured_agent}; "
                    + (f"available: {sample}" if sample else "no agents listed")
                ),
            )
        )

    return checks


def _check_audio_input(config: AppConfig | None) -> DoctorCheck:
    try:
        sounddevice = importlib.import_module("sounddevice")
    except Exception as error:
        return DoctorCheck(
            name="audio-input",
            status="fail",
            detail=f"cannot import sounddevice: {error}",
        )

    query_devices = getattr(sounddevice, "query_devices", None)
    if not callable(query_devices):
        return DoctorCheck(
            name="audio-input",
            status="fail",
            detail="sounddevice.query_devices is unavailable",
        )

    try:
        devices_obj = query_devices()
    except Exception as error:
        return DoctorCheck(
            name="audio-input",
            status="fail",
            detail=f"failed to query audio devices: {error}",
        )

    device_entries = _coerce_device_entries(devices_obj)
    if device_entries is None:
        return DoctorCheck(
            name="audio-input",
            status="warn",
            detail="unexpected audio device payload shape",
        )

    input_devices: list[Mapping[str, object]] = []
    for item in device_entries:
        max_inputs = _to_float(item.get("max_input_channels", 0.0))
        if max_inputs > 0:
            input_devices.append(item)
    if not input_devices:
        return DoctorCheck(
            name="audio-input",
            status="fail",
            detail="no input-capable microphone device detected",
        )

    default_index = _read_default_input_device_index(sounddevice)
    check_input_settings = getattr(sounddevice, "check_input_settings", None)
    if default_index is not None and callable(check_input_settings):
        sample_rate = float(config.sample_rate) if config is not None else 16000.0
        channels = config.channels if config is not None else 1
        try:
            _ = check_input_settings(
                device=default_index,
                channels=max(1, int(channels)),
                samplerate=sample_rate,
            )
        except Exception as error:
            return DoctorCheck(
                name="audio-input",
                status="warn",
                detail=f"default input exists but validation failed: {error}",
            )

    return DoctorCheck(
        name="audio-input",
        status="ok",
        detail=f"detected {len(input_devices)} input-capable device(s)",
    )


def _check_input_device_permissions(config: AppConfig | None) -> DoctorCheck:
    if not sys.platform.startswith("linux"):
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail="raw input permission check is only available on Linux",
        )

    try:
        evdev_module = importlib.import_module("evdev")
    except Exception as error:
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail=f"cannot import evdev for raw input check: {error}",
        )

    list_devices = getattr(evdev_module, "list_devices", None)
    input_device_ctor = getattr(evdev_module, "InputDevice", None)
    ecodes = getattr(evdev_module, "ecodes", None)
    if not callable(list_devices) or input_device_ctor is None or ecodes is None:
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail="evdev module is missing required APIs",
        )

    try:
        device_paths_obj = list_devices()
    except Exception as error:
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail=f"failed to list /dev/input devices: {error}",
        )

    if not isinstance(device_paths_obj, list):
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail="unexpected device-path payload from evdev",
        )

    device_paths = [str(path) for path in device_paths_obj]
    if not device_paths:
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail="no /dev/input/event* devices were found",
        )

    ev_key = int(getattr(ecodes, "EV_KEY", 1))
    btn_side = int(getattr(ecodes, "BTN_SIDE", 0x116))
    btn_extra = int(getattr(ecodes, "BTN_EXTRA", 0x117))
    side_button_codes = {btn_side, btn_extra}

    accessible = 0
    side_capable = 0
    permission_denied = 0

    for path in device_paths:
        try:
            device = input_device_ctor(path)
        except PermissionError:
            permission_denied += 1
            continue
        except Exception:
            continue

        try:
            capabilities_obj = device.capabilities()
            accessible += 1
            if isinstance(capabilities_obj, dict):
                keys_obj = capabilities_obj.get(ev_key, [])
                keys = {int(code) for code in keys_obj if isinstance(code, int)}
                if side_button_codes & keys:
                    side_capable += 1
        finally:
            try:
                device.close()
            except Exception:
                pass

    if accessible == 0 and permission_denied > 0:
        return DoctorCheck(
            name="input-device-permissions",
            status="fail",
            detail=(
                "cannot access /dev/input event devices (permission denied); "
                + "add user to input group or configure udev rules"
            ),
        )

    if accessible == 0:
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail="no readable /dev/input event devices were found",
        )

    rear_button = config.rear_button if config is not None else "x2"
    if side_capable == 0:
        return DoctorCheck(
            name="input-device-permissions",
            status="warn",
            detail=(
                f"{accessible} input device(s) readable but none expose side-button codes "
                + f"for rear={rear_button}"
            ),
        )

    return DoctorCheck(
        name="input-device-permissions",
        status="ok",
        detail=(
            f"{accessible} readable input device(s), "
            + f"{side_capable} with side-button capability"
        ),
    )


def _read_default_input_device_index(sounddevice: object) -> int | None:
    default_obj = getattr(sounddevice, "default", None)
    if default_obj is None:
        return None

    device_attr = getattr(default_obj, "device", None)
    if not isinstance(device_attr, tuple | list) or len(device_attr) < 1:
        return None

    raw_input_index = device_attr[0]
    if not isinstance(raw_input_index, int):
        return None
    if raw_input_index < 0:
        return None
    return raw_input_index


def _coerce_device_entries(devices_obj: object) -> list[Mapping[str, object]] | None:
    if isinstance(devices_obj, list):
        return [entry for entry in devices_obj if isinstance(entry, Mapping)]

    if isinstance(devices_obj, Iterable):
        entries: list[Mapping[str, object]] = []
        for entry in devices_obj:
            if isinstance(entry, Mapping):
                entries.append(entry)
        return entries

    return None


def _to_float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _check_hyprland_return_bind_conflict(config: AppConfig | None) -> DoctorCheck:
    bind_path = Path.home() / ".config/hypr/UserConfigs/UserKeybinds.conf"
    if not bind_path.exists():
        return DoctorCheck(
            name="hyprland-bind-conflict",
            status="warn",
            detail=f"file not found: {bind_path}",
        )

    rear_button = config.rear_button if config is not None else "x2"
    rear_mouse_code = "mouse:275" if rear_button == "x1" else "mouse:276"

    lines = bind_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if rear_mouse_code in line and "sendshortcut" in line and "Return" in line:
            return DoctorCheck(
                name="hyprland-bind-conflict",
                status="fail",
                detail=(
                    f"conflicting return bind found at {bind_path}:{idx}; "
                    + "disable it to let VibeMouse control rear-button behavior"
                ),
            )

    return DoctorCheck(
        name="hyprland-bind-conflict",
        status="ok",
        detail=f"no conflicting {rear_mouse_code} return bind found",
    )


def _check_user_service_state() -> DoctorCheck:
    try:
        probe = subprocess.run(
            ["systemctl", "--user", "is-active", "vibemouse.service"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return DoctorCheck(
            name="user-service",
            status="warn",
            detail=f"could not query service state: {error}",
        )

    state = probe.stdout.strip() or "unknown"
    if state == "active":
        return DoctorCheck(
            name="user-service",
            status="ok",
            detail="vibemouse.service is active",
        )

    return DoctorCheck(
        name="user-service",
        status="warn",
        detail=f"vibemouse.service state is {state}",
    )


def _parse_openclaw_command(raw: str) -> list[str] | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        parts = shlex.split(cleaned)
    except ValueError:
        return None
    if not parts:
        return None
    return parts


def _print_checks(checks: list[DoctorCheck]) -> None:
    for check in checks:
        badge = {
            "ok": "[OK]",
            "warn": "[WARN]",
            "fail": "[FAIL]",
        }.get(check.status, "[INFO]")
        print(f"{badge} {check.name}: {check.detail}")
