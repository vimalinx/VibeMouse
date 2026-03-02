# VibeMouse AI Assistant Deployment & Adaptation Guide

This guide is for AI assistants (and engineers using AI assistants) to deploy VibeMouse on a new machine and adapt it to a new platform safely.

Use this as the source-of-truth playbook when adding Windows/macOS support or custom desktop integration.

## 1) Project Goal and Non-Negotiable Behavior

VibeMouse is a side-button voice workflow tool.

Required behavior:
- Front side button: start/stop recording
- Rear side button when idle: send Enter
- Rear side button while recording: stop recording and dispatch transcript to OpenClaw
- Fallbacks must preserve user output (never silently lose text)

Do not break this state machine while adapting platforms.

## 2) Core Architecture Map

Key modules:
- `vibemouse/main.py`: CLI entry (`run`, `doctor`)
- `vibemouse/app.py`: runtime orchestration + state machine + worker lifecycle
- `vibemouse/mouse_listener.py`: side-button capture + gesture path
- `vibemouse/audio.py`: microphone recording
- `vibemouse/transcriber.py`: ASR backend selection/transcription
- `vibemouse/output.py`: text output routing + OpenClaw dispatch + fallback
- `vibemouse/system_integration.py`: platform adapter boundary
- `vibemouse/doctor.py`: environment and runtime diagnostics
- `vibemouse/config.py`: env config contract

## 3) Platform Adaptation Boundary (Most Important)

When adapting a platform, implement/extend `SystemIntegration` in `vibemouse/system_integration.py`.

Methods used by runtime:
- `is_hyprland`
- `send_shortcut(mod, key)`
- `active_window()`
- `cursor_position()`
- `move_cursor(x, y)`
- `switch_workspace(direction)`
- `is_text_input_focused()`
- `send_enter_via_accessibility()`
- `is_terminal_window_active()`
- `paste_shortcuts(terminal_active)`

Rule: add platform-specific behavior here first; avoid spreading platform logic across `app.py` and `output.py`.

## 4) Dependencies and Download Sources

### Required foundations
- Python 3.10-3.12 (currently prefer 3.12; 3.13+ dependency chain is not stable yet): https://www.python.org/downloads/
- pip: https://pip.pypa.io/en/stable/installation/

### Runtime and audio
- PortAudio: http://www.portaudio.com/download.html
- libsndfile: https://github.com/libsndfile/libsndfile
- `sounddevice`: https://pypi.org/project/sounddevice/
- `soundfile`: https://pypi.org/project/soundfile/

### Input and desktop integration
- `pynput`: https://pypi.org/project/pynput/
- `evdev` (Linux): https://python-evdev.readthedocs.io/en/latest/
- PyGObject / AT-SPI: https://pygobject.gnome.org/

### ASR and model stack
- PyTorch: https://pypi.org/project/torch/
- Torchaudio: https://pypi.org/project/torchaudio/
- FunASR: https://pypi.org/project/funasr/
- FunASR ONNX: https://pypi.org/project/funasr-onnx/
- ONNX Runtime: https://pypi.org/project/onnxruntime/
- OpenVINO: https://pypi.org/project/openvino/
- ModelScope: https://pypi.org/project/modelscope/

### OpenClaw integration target
- OpenClaw repo: https://github.com/openclaw/openclaw

The project’s pinned Python dependencies are defined in `pyproject.toml`.

## 5) Deployment Procedure (Assistant-Executable)

Fastest path (recommended):

```bash
bash scripts/auto-deploy.sh --preset stable
```

If the default `python3` is 3.13+, the script will auto-try `python3.12`.
You can also force interpreter selection:

```bash
VIBEMOUSE_PYTHON_BIN=python3.12 bash scripts/auto-deploy.sh --preset stable
```

Preset choices: `stable`, `fast`, `low-resource`.

For non-Linux platforms (macOS/Windows), prefer:

```bash
bash scripts/auto-deploy.sh --preset stable --skip-systemctl
```

Direct command alternative:

```bash
vibemouse deploy --preset stable
```

1. Clone and install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

2. Run diagnostics first
```bash
vibemouse doctor
vibemouse doctor --fix
```

3. Ensure OpenClaw route works
```bash
openclaw agent --agent main --message "ping" --json
```

4. Start runtime
```bash
vibemouse
```

First-run notes:
- Initial model download may be hundreds of MB to around 1 GB.
- On macOS, grant Accessibility and Input Monitoring permissions to your terminal app.

5. Validate behavior matrix manually
- idle + rear -> Enter
- recording + rear -> OpenClaw dispatch

## 6) Service Deployment (Linux user service)

Recommended user service file location:
- `~/.config/systemd/user/vibemouse.service`

Minimum lifecycle commands:
```bash
systemctl --user daemon-reload
systemctl --user enable --now vibemouse.service
systemctl --user status vibemouse.service
```

## 7) Environment Contract (Critical Variables)

OpenClaw:
- `VIBEMOUSE_OPENCLAW_COMMAND`
- `VIBEMOUSE_OPENCLAW_AGENT`
- `VIBEMOUSE_OPENCLAW_TIMEOUT_S`
- `VIBEMOUSE_OPENCLAW_RETRIES`

Buttons/state:
- `VIBEMOUSE_FRONT_BUTTON`
- `VIBEMOUSE_REAR_BUTTON`
- `VIBEMOUSE_ENTER_MODE`

ASR performance:
- `VIBEMOUSE_BACKEND`
- `VIBEMOUSE_DEVICE`
- `VIBEMOUSE_PREWARM_ON_START`

Gesture path:
- `VIBEMOUSE_GESTURES_ENABLED`
- `VIBEMOUSE_GESTURE_TRIGGER_BUTTON`
- `VIBEMOUSE_GESTURE_THRESHOLD_PX`
- `VIBEMOUSE_GESTURE_FREEZE_POINTER`

## 8) Adaptation Checklist for New Platform

When adding Windows/macOS support:

1. Add platform class in `system_integration.py`.
2. Implement shortcut send + active window + focus probe with native APIs.
3. Define terminal detection hints and paste shortcut strategy.
4. Keep fallback chain intact in `output.py`.
5. Verify rear-button state machine in `app.py` unchanged.
6. Add tests in:
   - `tests/test_system_integration.py`
   - `tests/test_output.py`
   - `tests/test_app.py`
7. Run full verification:
```bash
python -m compileall vibemouse
python -m unittest discover -s tests -p "test_*.py"
vibemouse doctor
```

## 9) Regression Gates (Must Pass Before Merge)

- No change to front/rear state semantics
- OpenClaw dispatch keeps fallback path
- Doctor command still reports useful failures/warnings
- Existing tests pass; new platform tests added
- No destructive change to Linux Hyprland path

## 10) Prompt Template for AI Assistants

Use this prompt when asking an AI assistant to adapt VibeMouse:

```text
You are adapting VibeMouse to <TARGET_PLATFORM>.

Constraints:
1) Preserve button state machine:
   - front: start/stop recording
   - rear idle: Enter
   - rear recording: OpenClaw dispatch
2) Implement platform logic only via system_integration.py first.
3) Preserve fallback behavior (clipboard fallback on OpenClaw spawn failure).
4) Add/adjust tests in test_system_integration.py, test_output.py, test_app.py.
5) Run compileall + full unit tests + vibemouse doctor and report results.

Deliver:
- code changes
- test changes
- verification evidence
- known platform-specific limitations
```

This keeps adaptation focused, testable, and safe for daily usage.
