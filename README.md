# VibeMouse

Mouse-side-button voice input for VibeCoding.

中文文档：[`README.zh-CN.md`](./README.zh-CN.md)

AI adaptation guides:
- English: [`docs/AI_ASSISTANT_DEPLOYMENT.md`](./docs/AI_ASSISTANT_DEPLOYMENT.md)
- 中文：[`docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md`](./docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md)
- AI debug runbook: [`docs/AI_DEBUG_RUNBOOK.md`](./docs/AI_DEBUG_RUNBOOK.md)

## What This Project Does

VibeMouse binds your coding speech workflow to mouse side buttons:
- Front side button: start/stop recording
- Rear side button while idle: send Enter
- Rear side button while recording: stop recording and output the transcript through the default text route

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
   - Text typing / clipboard output, with fallback and reason tracking
7. `vibemouse/system_integration.py`
   - Platform adapter boundary (Hyprland now, Windows/macOS extension points prepared)
8. `vibemouse/doctor.py`
   - Built-in diagnostics for env, input permissions, and known conflicts

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
export VIBEMOUSE_BACKEND=funasr_onnx
export VIBEMOUSE_DEVICE=cpu
vibemouse
```

Default install is ONNX-first for smaller deployment footprint.

- Optional PyTorch backend (GPU/advanced fallback): `pip install -e ".[pt]"`
- Optional local Opus-MT translation dependencies: `pip install -e ".[translation]"`
- Optional Intel NPU dependencies: `pip install -e ".[npu]"`

## Dictation Profiles And Dictionary

VibeMouse now exposes two user-facing dictation modes instead of raw model names:
- `Fast`: lower latency, stable daily driver, current SenseVoice path
- `Enhanced`: accuracy-first path, forwards weighted hotwords into the FunASR backend

Profiles are assigned per output target:
- `default`

Dictionary entries are shared across both targets and use this shape:

```json
{
  "term": "Codex",
  "phrases": ["codex", "code x", "扣带思"],
  "weight": 8,
  "scope": "both",
  "enabled": true
}
```

Behavior:
- `Enhanced` uses `phrases` + `weight` for hotword biasing during decoding
- both `Fast` and `Enhanced` normalize matched phrases back to the canonical `term`
- `scope` can be `default` or `both`
- if `Enhanced` is unavailable, VibeMouse reports the failure explicitly instead of silently downgrading

See [`shared/examples/config.example.json`](./shared/examples/config.example.json) for a complete example.

## Settings UI

Run the local settings UI:

```bash
vibemouse settings --open-browser
```

If you do not want to auto-open the browser:

```bash
vibemouse settings
```

The UI lets you:
- switch the default dictation profile between `Fast` and `Enhanced`
- add, edit, enable, or disable dictionary entries
- inspect backend availability and dependency errors

## Dictation Evaluation Harness

To compare profile behavior on your own recordings, create a JSONL fixture like
[`shared/examples/dictation_eval.jsonl`](./shared/examples/dictation_eval.jsonl) and run:

```bash
python scripts/eval_dictation_profiles.py \
  --dataset shared/examples/dictation_eval.jsonl \
  --profile fast \
  --profile enhanced
```

The script reports:
- exact text match rate
- dictionary term hit rate
- backend availability / unavailability reasons

The example fixture uses placeholder audio paths. Replace them with real local WAV paths before running the script.

### One-command auto deploy (recommended)

```bash
bash scripts/auto-deploy.sh --preset stable
```

This command bootstraps `.venv`, installs VibeMouse, generates service/env files,
enables `systemd --user` service, and runs `vibemouse doctor`.

Available presets:
- `stable`: balanced daily-driver defaults
- `fast`: lower debounce for faster side-button response
- `low-resource`: lower background footprint defaults

Examples:

```bash
# High reliability profile
bash scripts/auto-deploy.sh --preset stable

# Keep resources low
bash scripts/auto-deploy.sh --preset low-resource
```

## Default Mapping and State Logic

- `VIBEMOUSE_FRONT_BUTTON` default: `x1`
- `VIBEMOUSE_REAR_BUTTON` default: `x2`

State matrix:
- Idle + rear press -> Enter (`VIBEMOUSE_ENTER_MODE`)
- Recording + rear press -> stop recording + default text output

If your hardware labels are reversed:

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
```

## Runtime Settings Reload

The local settings UI asks the running daemon to reload after saving config.
If you expose the command server beyond the default loopback workflow, set:
- `VIBEMOUSE_COMMAND_AUTH_TOKEN`
- `runtime.command_auth_token` in `config.json`

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
- `--command-auth-token reload-secret`
- `--log-file ~/.local/state/vibemouse/service.log`
- `--skip-systemctl`
- `--dry-run`

Persistent debug logs (recommended):

```bash
tail -f ~/.local/state/vibemouse/service.log
```

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
| `VIBEMOUSE_COMMAND_AUTH_TOKEN` | unset | Optional token required by local command-server clients |

Full configuration source of truth: `vibemouse/config/schema.py`.

## Troubleshooting Shortlist

### Postmortem: "Everything stopped working" (record/gesture/enter)

When users report that recording, right-button gestures, and Enter all fail together,
the most common root cause is **mouse side-button event mismatch**, not a dead service.

Typical failure pattern:
- Service is `active`, but button actions never trigger.
- Hyprland workspace commands still return `ok` when run manually.
- User perception: "all features are broken".

Real root causes we hit:
1. Side-button codes were only matched as `BTN_SIDE`/`BTN_EXTRA`.
2. Some mice emit `BTN_BACK`/`BTN_FORWARD` aliases instead.
3. Runtime env had action mappings, but listener never recognized raw events.

Current fix in code:
- `x1` accepts `{BTN_SIDE, BTN_BACK}`
- `x2` accepts `{BTN_EXTRA, BTN_FORWARD}`

Fast verification order (recommended):
1. `systemctl --user is-active vibemouse.service`
2. `hyprctl dispatch workspace e-1` and `hyprctl dispatch workspace e+1`
3. `vibemouse doctor`
4. Confirm runtime env from `/proc/<MainPID>/environ`:
   - `VIBEMOUSE_GESTURE_TRIGGER_BUTTON`
   - `VIBEMOUSE_GESTURE_LEFT_ACTION`
   - `VIBEMOUSE_GESTURE_RIGHT_ACTION`
   - `VIBEMOUSE_FRONT_BUTTON` / `VIBEMOUSE_REAR_BUTTON`

If (1)-(3) pass but buttons still do nothing, debug listener code-path first.

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

### Settings changes do not apply to the running daemon

```bash
cat "${XDG_RUNTIME_DIR:-/tmp}/vibemouse-status.json"
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
- [`docs/AI_DEBUG_RUNBOOK.md`](./docs/AI_DEBUG_RUNBOOK.md)

It contains architecture contracts, dependency download links, adaptation workflow,
and a prompt template for autonomous platform adaptation.

## License

Source code is licensed under Apache-2.0. See `LICENSE`.

Third-party and model asset notices: `THIRD_PARTY_NOTICES.md`.
