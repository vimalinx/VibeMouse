# VibeMouse

**Mouse-side-button voice input for VibeCoding on Linux.**

中文文档：[`README.zh-CN.md`](./README.zh-CN.md)

VibeMouse turns your mouse side buttons into a fast coding workflow:

- 🎙️ Press side button to start/stop recording
- ✍️ Auto speech-to-text with SenseVoice
- ⌨️ Type into focused input, or fallback to clipboard
- ↩️ Rear button sends Enter (or sends transcript to OpenClaw while recording)

If you spend hours in ChatGPT / Claude / IDEs and want to keep one hand on the mouse, this is for you.

---

## Why VibeMouse?

When VibeCoding, your flow is usually:

1. Think
2. Speak prompt
3. Submit

VibeMouse binds that to mouse side buttons so you can do it with minimal context switching.

---

## Features

- Global mouse side-button listening
- Start/stop recording with one side button
- Speech recognition using SenseVoice
- Smart output routing:
  - If focused element is editable → type text directly
  - Otherwise → copy text to clipboard (or auto paste when enabled)
- Rear button behavior by state:
  - Idle: send Enter
  - Recording: stop recording and send transcript to OpenClaw
- CPU-first stable default (works reliably)
- Optional backend switching (`funasr` / `funasr_onnx`)

---

## Current Platform

- Linux
- Python 3.10+

---

## Quick Start

### 1) Install system packages (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-atspi-2.0 portaudio19-dev libsndfile1
```

### 2) Install VibeMouse

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### 3) Run (recommended stable mode)

```bash
export VIBEMOUSE_BACKEND=auto
export VIBEMOUSE_DEVICE=cpu
vibemouse
```

---

## Default Button Mapping

- `x1` → voice button (start/stop recording)
- `x2` → Enter (idle) / OpenClaw submit (while recording)

If your mouse is reversed:

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
vibemouse
```

---

## How It Works

1. Press voice side button once → recording starts
2. Press again → recording stops, transcription runs
3. If current focus is editable input → text is typed
4. Otherwise text is copied to clipboard
5. Press rear side button:
   - idle mode: send Enter
   - recording mode: stop recording and send transcript to OpenClaw

---

## Configuration

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `VIBEMOUSE_BACKEND` | `auto` | `auto` / `funasr` / `funasr_onnx` |
| `VIBEMOUSE_MODEL` | `iic/SenseVoiceSmall` | Model id/path |
| `VIBEMOUSE_DEVICE` | `cpu` | Preferred device (`cpu`, `cuda:0`, `npu:0`) |
| `VIBEMOUSE_FALLBACK_CPU` | `true` | Fallback to CPU if preferred device fails |
| `VIBEMOUSE_BUTTON_DEBOUNCE_MS` | `150` | Ignore repeated side-button presses within this window |
| `VIBEMOUSE_GESTURES_ENABLED` | `false` | Enable side-button mouse gesture recognition |
| `VIBEMOUSE_GESTURE_TRIGGER_BUTTON` | `rear` | Gesture trigger button (`front`, `rear`, or `right`) |
| `VIBEMOUSE_GESTURE_THRESHOLD_PX` | `120` | Minimum movement required to treat input as gesture |
| `VIBEMOUSE_GESTURE_FREEZE_POINTER` | `true` | Grab mouse device during gesture to prevent pointer drift |
| `VIBEMOUSE_GESTURE_RESTORE_CURSOR` | `true` | Restore cursor position after recognized gesture action |
| `VIBEMOUSE_GESTURE_UP_ACTION` | `record_toggle` | Action for `up` gesture: `record_toggle`, `send_enter`, `workspace_left`, `workspace_right`, `noop` |
| `VIBEMOUSE_GESTURE_DOWN_ACTION` | `noop` | Action for `down` gesture: `record_toggle`, `send_enter`, `workspace_left`, `workspace_right`, `noop` |
| `VIBEMOUSE_GESTURE_LEFT_ACTION` | `noop` | Action for `left` gesture: `record_toggle`, `send_enter`, `workspace_left`, `workspace_right`, `noop` |
| `VIBEMOUSE_GESTURE_RIGHT_ACTION` | `send_enter` | Action for `right` gesture: `record_toggle`, `send_enter`, `workspace_left`, `workspace_right`, `noop` |
| `VIBEMOUSE_ENTER_MODE` | `enter` | Rear button enter mode: `enter`, `ctrl_enter`, `shift_enter`, `none` |
| `VIBEMOUSE_AUTO_PASTE` | `false` | Auto paste with Ctrl+V after copying fallback text |
| `VIBEMOUSE_OPENCLAW_COMMAND` | `openclaw` | OpenClaw CLI command prefix. Example: `openclaw --profile prod` |
| `VIBEMOUSE_OPENCLAW_AGENT` | `main` | Target agent name passed as `--agent` (set this to your own local assistant id when deploying) |
| `VIBEMOUSE_OPENCLAW_TIMEOUT_S` | `20.0` | Timeout in seconds for `openclaw agent` command |
| `VIBEMOUSE_TRUST_REMOTE_CODE` | `false` | Set `true` only for trusted models that require remote code |
| `VIBEMOUSE_PREWARM_ON_START` | `true` | Preload ASR backend at startup to reduce first-transcription latency |
| `VIBEMOUSE_STATUS_FILE` | `$XDG_RUNTIME_DIR/vibemouse-status.json` | Runtime status file used by bar indicators |
| `VIBEMOUSE_LANGUAGE` | `auto` | `auto`, `zh`, `en`, `yue`, `ja`, `ko` |
| `VIBEMOUSE_USE_ITN` | `true` | Enable text normalization |
| `VIBEMOUSE_ENABLE_VAD` | `true` | Enable VAD |
| `VIBEMOUSE_VAD_MAX_SEGMENT_MS` | `30000` | Max VAD segment length |
| `VIBEMOUSE_MERGE_VAD` | `true` | Merge VAD segments |
| `VIBEMOUSE_MERGE_LENGTH_S` | `15` | Merge threshold in seconds |
| `VIBEMOUSE_SAMPLE_RATE` | `16000` | Recording sample rate |
| `VIBEMOUSE_CHANNELS` | `1` | Recording channels |
| `VIBEMOUSE_DTYPE` | `float32` | Recording dtype |
| `VIBEMOUSE_FRONT_BUTTON` | `x1` | Voice button (`x1` or `x2`) |
| `VIBEMOUSE_REAR_BUTTON` | `x2` | Enter button (`x1` or `x2`) |
| `VIBEMOUSE_TEMP_DIR` | system temp | Temp audio path |

---

## Troubleshooting

### Side button not detected

Likely Linux input permission issue. Add your user to `input` group and relogin:

```bash
sudo usermod -aG input $USER
```

### Text is not typed into app

Some apps do not expose editable accessibility metadata. In that case VibeMouse falls back to clipboard by design.

On Hyprland, terminal windows (foot/kitty/alacritty/wezterm, etc.) use terminal-friendly paste shortcuts automatically (`Ctrl+Shift+V`, then `Shift+Insert` fallback).

### Rear button Enter feels unreliable

Try a different submit combo and reduce accidental repeated clicks:

```bash
export VIBEMOUSE_ENTER_MODE=ctrl_enter
export VIBEMOUSE_BUTTON_DEBOUNCE_MS=220
systemctl --user restart vibemouse.service
```

For Hyprland, you can move Enter to a compositor-level bind and disable VibeMouse rear-button Enter:

```ini
# ~/.config/hypr/UserConfigs/UserKeybinds.conf
bind = , mouse:276, sendshortcut, , Return, activewindow
# If your physical rear button is X1, use mouse:275 instead
```

```bash
export VIBEMOUSE_ENTER_MODE=none
systemctl --user restart vibemouse.service
hyprctl reload config-only
```

### Rear button in recording mode does not reach OpenClaw

Check OpenClaw CLI availability first:

```bash
openclaw agent --message "ping" --json
```

If you use a custom binary path/profile, set:

```bash
export VIBEMOUSE_OPENCLAW_COMMAND="openclaw --profile prod"
export VIBEMOUSE_OPENCLAW_AGENT="ops"
systemctl --user restart vibemouse.service
```

Deployment tip: if you run multiple local assistants, point `VIBEMOUSE_OPENCLAW_AGENT`
to your own assistant id (for example `main`, `ops`, or your custom agent name).

### Mouse gestures do not trigger actions

Enable gestures and choose a trigger button first:

```bash
export VIBEMOUSE_GESTURES_ENABLED=true
export VIBEMOUSE_GESTURE_TRIGGER_BUTTON=rear
export VIBEMOUSE_GESTURE_THRESHOLD_PX=120
systemctl --user restart vibemouse.service
```

Default gesture mapping is:

- `up` -> toggle recording
- `right` -> send Enter
- `down` / `left` -> no-op

You can remap each direction with `VIBEMOUSE_GESTURE_*_ACTION`.

If pointer drift is still noticeable while holding the trigger button, keep
`VIBEMOUSE_GESTURE_FREEZE_POINTER=true` (default). This grabs the mouse device
during gesture capture on evdev-capable setups such as Hyprland + Arch.

### Hyprland right-button workspace gestures

If you want "hold right mouse button + swipe" to switch workspaces:

```bash
export VIBEMOUSE_GESTURES_ENABLED=true
export VIBEMOUSE_GESTURE_TRIGGER_BUTTON=right
export VIBEMOUSE_GESTURE_LEFT_ACTION=workspace_left
export VIBEMOUSE_GESTURE_RIGHT_ACTION=workspace_right
export VIBEMOUSE_GESTURE_THRESHOLD_PX=190
export VIBEMOUSE_GESTURE_FREEZE_POINTER=false
export VIBEMOUSE_GESTURE_RESTORE_CURSOR=true
export VIBEMOUSE_GESTURE_UP_ACTION=noop
export VIBEMOUSE_GESTURE_DOWN_ACTION=noop
systemctl --user restart vibemouse.service
```

### First transcription is slow after startup or long idle

Enable startup prewarm so the ASR backend loads before your first dictation:

```bash
export VIBEMOUSE_PREWARM_ON_START=true
systemctl --user restart vibemouse.service
```

Then confirm prewarm with:

```bash
journalctl --user -u vibemouse.service -n 30 --no-pager | rg "prewarm"
```

### Recording works but recognition empty

Check microphone gain/input source first. Also verify your sample is not silent.

---

## About NPU/OpenVINO

NPU support depends on model graph compatibility with the NPU compiler.

In this project, **CPU default is intentional** for stability. If NPU compile fails, app behavior remains usable via CPU fallback.

---

## Run as background process (optional)

You can run with tmux/screen/systemd for always-on workflow.

Example (tmux):

```bash
tmux new -d -s vibemouse "source .venv/bin/activate && vibemouse"
tmux attach -t vibemouse
```

---

## Project Layout

```text
vibemouse/
  app.py           # app orchestration
  audio.py         # recording
  mouse_listener.py# side-button listener
  transcriber.py   # ASR backends
  output.py        # type/clipboard/enter output
  config.py        # env config
  main.py          # CLI entry
```

---

## Development

```bash
python -m compileall vibemouse
python -m pip check
```

---

## License

VibeMouse source code is licensed under Apache-2.0. See `LICENSE`.

Third-party and model-asset notices are documented in `THIRD_PARTY_NOTICES.md`.

Before redistributing binaries or bundled models, review LGPL obligations
(`pynput`, `PyGObject`) and verify the exact license of the model IDs you ship.
