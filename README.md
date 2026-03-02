# VibeMouse

Mouse-side-button voice input for VibeCoding.

中文文档：[`README.zh-CN.md`](./README.zh-CN.md)

AI adaptation guides:
- English: [`docs/AI_ASSISTANT_DEPLOYMENT.md`](./docs/AI_ASSISTANT_DEPLOYMENT.md)
- 中文：[`docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md`](./docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md)

## What This Project Does

VibeMouse binds your coding speech workflow to mouse side buttons:
- Front side button: start/stop recording
- Rear side button while idle: send Enter
- Rear side button while recording: stop recording and route transcript to OpenClaw

Core goals are low friction, stable daily use, and graceful fallback when any subsystem fails.

## Runtime Architecture (Core)

The runtime is event-driven and split by responsibility:

1. `vibemouse/main.py`
   - CLI entry (`run` / `doctor`)
2. `vibemouse/app.py`
   - Orchestrates button events, recording state, transcription workers, and final output routing
3. `vibemouse/mouse_listener.py`
   - Captures side buttons and gestures (`evdev` first, fallback path available)
4. `vibemouse/audio.py`
   - Records audio to temp WAV
5. `vibemouse/transcriber.py`
   - SenseVoice backend selection and transcription
6. `vibemouse/output.py`
   - Text typing / clipboard / OpenClaw dispatch, with fallback and reason tracking
7. `vibemouse/system_integration.py`
   - Platform adapter boundary (Hyprland now, Windows/macOS extension points prepared)
8. `vibemouse/doctor.py`
   - Built-in diagnostics for env, OpenClaw, input permissions, and known conflicts

## Quick Start (Linux)

### Ubuntu / Debian packages

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-atspi-2.0 portaudio19-dev libsndfile1
```

### Arch packages

```bash
sudo pacman -Syu --needed python python-pip python-gobject portaudio libsndfile
```

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### Run

```bash
export VIBEMOUSE_BACKEND=auto
export VIBEMOUSE_DEVICE=cpu
vibemouse
```

### One-command auto deploy (recommended)

```bash
bash scripts/auto-deploy.sh --preset stable
```

This command bootstraps `.venv`, installs VibeMouse, generates service/env files,
enables `systemd --user` service, and runs `vibemouse doctor`.

Available presets:
- `stable`: balanced daily-driver defaults
- `fast`: lower debounce + higher OpenClaw retries
- `low-resource`: lower background footprint defaults

Examples:

```bash
# High reliability profile
bash scripts/auto-deploy.sh --preset stable

# Keep resources low
bash scripts/auto-deploy.sh --preset low-resource

# Custom OpenClaw target assistant
bash scripts/auto-deploy.sh --preset stable --openclaw-agent ops
```

## Default Mapping and State Logic

- `VIBEMOUSE_FRONT_BUTTON` default: `x1`
- `VIBEMOUSE_REAR_BUTTON` default: `x2`

State matrix:
- Idle + rear press -> Enter (`VIBEMOUSE_ENTER_MODE`)
- Recording + rear press -> stop recording + OpenClaw dispatch

If your hardware labels are reversed:

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
```

## OpenClaw Integration (Core)

OpenClaw route is explicit and configurable:
- `VIBEMOUSE_OPENCLAW_COMMAND` (default `openclaw`)
- `VIBEMOUSE_OPENCLAW_AGENT` (default `main`)
- `VIBEMOUSE_OPENCLAW_TIMEOUT_S` (default `20.0`)
- `VIBEMOUSE_OPENCLAW_RETRIES` (default `0`)

Dispatch behavior:
- Fast fire-and-forget spawn to avoid blocking UI interaction
- Route result includes reason (`dispatched`, `dispatched_after_retry_*`, `spawn_error:*`, etc.)
- Clipboard fallback if command is invalid or spawn fails

Deployment tip: if you run your own local assistant setup, set
`VIBEMOUSE_OPENCLAW_AGENT` to your own assistant ID.

## Built-in Doctor

Run diagnostics:

```bash
vibemouse doctor
```

Apply safe auto-fixes first, then re-check:

```bash
vibemouse doctor --fix
```

Current checks include:
- Config load validity
- OpenClaw command resolution + agent existence
- Microphone input availability
- Linux input device permissions / side-button capability
- Hyprland rear-button Return bind conflicts
- `systemctl --user` service activity

Current auto-fixes (`--fix`) include:
- Auto-disable conflicting Hyprland side-button Return binds
- Attempt to restart inactive `vibemouse.service`

Exit code is non-zero when any `FAIL` check exists.

## Deploy Command

The deploy command is scriptable and can be used directly:

```bash
vibemouse deploy --preset stable
```

Useful flags:
- `--preset stable|fast|low-resource`
- `--openclaw-command "openclaw --profile prod"`
- `--openclaw-agent main`
- `--openclaw-retries 2`
- `--skip-systemctl`
- `--dry-run`

## Frequently Used Variables

| Variable | Default | Purpose |
|---|---|---|
| `VIBEMOUSE_ENTER_MODE` | `enter` | Rear-button submit mode (`enter`, `ctrl_enter`, `shift_enter`, `none`) |
| `VIBEMOUSE_AUTO_PASTE` | `false` | Auto paste when route falls back to clipboard |
| `VIBEMOUSE_GESTURES_ENABLED` | `false` | Enable gesture recognition |
| `VIBEMOUSE_GESTURE_TRIGGER_BUTTON` | `rear` | Gesture trigger (`front`, `rear`, `right`) |
| `VIBEMOUSE_GESTURE_THRESHOLD_PX` | `120` | Gesture movement threshold |
| `VIBEMOUSE_GESTURE_FREEZE_POINTER` | `true` | Freeze pointer during gesture capture |
| `VIBEMOUSE_PREWARM_ON_START` | `true` | Preload ASR on startup to reduce first-use latency |
| `VIBEMOUSE_PREWARM_DELAY_S` | `0.0` | Delay ASR prewarm after startup to improve initial responsiveness |
| `VIBEMOUSE_STATUS_FILE` | `$XDG_RUNTIME_DIR/vibemouse-status.json` | Runtime status for bars/widgets |

Full configuration source of truth: `vibemouse/config.py`.

## Troubleshooting Shortlist

### Rear button still sends Enter while recording

Check Hyprland-level hard bind conflict in
`~/.config/hypr/UserConfigs/UserKeybinds.conf` and remove lines like:

```ini
bind = , mouse:275, sendshortcut, , Return, activewindow
bind = , mouse:276, sendshortcut, , Return, activewindow
```

Then reload:

```bash
hyprctl reload config-only
```

### OpenClaw route not working

```bash
openclaw agent --agent main --message "ping" --json
vibemouse doctor
```

### Side button not detected on Linux

```bash
sudo usermod -aG input $USER
# relogin required
```

## For AI Assistants and Platform Adapters

Use this guide when adapting to Windows/macOS or custom environments:

- [`docs/AI_ASSISTANT_DEPLOYMENT.md`](./docs/AI_ASSISTANT_DEPLOYMENT.md)
- [`docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md`](./docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md)

It contains architecture contracts, dependency download links, adaptation workflow,
and a prompt template for autonomous platform adaptation.

## License

Source code is licensed under Apache-2.0. See `LICENSE`.

Third-party and model asset notices: `THIRD_PARTY_NOTICES.md`.
