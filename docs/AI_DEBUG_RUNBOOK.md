# VibeMouse AI Debug Runbook (Service + Side Buttons + Gestures)

Use this when users report:
- "recording does not start"
- "right-button gesture does not switch workspace"
- "rear button enter does not work"
- or "everything broke at once"

## 0) High-probability diagnosis

If service is active but all button-triggered behaviors fail together, suspect:
1. Side-button raw event code mismatch (`BTN_SIDE/BTN_EXTRA` vs `BTN_BACK/BTN_FORWARD`), or
2. Runtime env mapping not loaded into the service process.

Do **not** assume service crash first.

## 0.1) Core chain snapshot (what matters in production)

Current Linux+Hyprland production chain is intentionally narrowed to:

1. `main.py` -> `load_config()` -> `VoiceMouseApp.run()`
2. `mouse_listener.py` (`evdev` primary, `pynput` fallback)
3. `audio.py` (record start/stop + sample-rate fallback)
4. `transcriber.py` (`funasr_onnx` runtime only)
5. `output.py` (enter / typed / clipboard / OpenClaw route)
6. `system_integration.py` (`HyprlandSystemIntegration` or `NoopSystemIntegration`)

Simplified/removed paths:
- Windows/macOS integration branches are removed from runtime factory.
- `funasr` and `auto` backend execution paths are removed; values are compatibility-mapped to ONNX.

Kept intentionally:
- `pynput` fallback in listener (evdev failure resilience)
- `doctor` and `deploy` operational checks

---

## 1) Service and environment sanity

```bash
systemctl --user is-active vibemouse.service
systemctl --user status vibemouse.service --no-pager
```

Read effective runtime env from service process:

```bash
pid=$(systemctl --user show vibemouse.service --property=MainPID --value)
python3 - <<'PY'
import subprocess
pid=subprocess.check_output(['systemctl','--user','show','vibemouse.service','--property=MainPID','--value'],text=True).strip()
env=open(f'/proc/{pid}/environ','rb').read().split(b'\0')
keys=[
  b'VIBEMOUSE_FRONT_BUTTON', b'VIBEMOUSE_REAR_BUTTON',
  b'VIBEMOUSE_GESTURES_ENABLED', b'VIBEMOUSE_GESTURE_TRIGGER_BUTTON',
  b'VIBEMOUSE_GESTURE_LEFT_ACTION', b'VIBEMOUSE_GESTURE_RIGHT_ACTION',
  b'VIBEMOUSE_ENTER_MODE', b'WAYLAND_DISPLAY', b'HYPRLAND_INSTANCE_SIGNATURE'
]
for k in keys:
    v=next((x.split(b'=',1)[1] for x in env if x.startswith(k+b'=')),None)
    print((k+b'='+(v if v else b'<unset>')).decode('utf-8','ignore'))
PY
```

Expected for right-button workspace gestures:
- `VIBEMOUSE_GESTURES_ENABLED=true`
- `VIBEMOUSE_GESTURE_TRIGGER_BUTTON=right`
- `VIBEMOUSE_GESTURE_LEFT_ACTION=workspace_left`
- `VIBEMOUSE_GESTURE_RIGHT_ACTION=workspace_right`

---

## 2) Verify compositor dispatch layer independently

```bash
hyprctl dispatch workspace e-1
hyprctl dispatch workspace e+1
```

If both return `ok`, workspace switching path is healthy; issue is likely listener/input side.

---

## 3) Check Hyprland bind conflicts

```bash
hyprctl binds
```

Also inspect config files for side-button hard binds that steal events:

```bash
grep -R --line-number -E 'mouse:275|mouse:276|mouse:277|mouse:278|sendshortcut|Return' ~/.config/hypr
```

If conflicting side-button binds exist, disable them and reload:

```bash
hyprctl reload config-only
```

---

## 4) Recorder sanity (without button path)

```bash
vibemouse doctor
```

If sample-rate errors appear (`paInvalidSampleRate`), set a stable rate in deploy env, e.g.:

```bash
VIBEMOUSE_SAMPLE_RATE=48000
```

Then restart service.

---

## 5) Known side-button code compatibility requirement

Some mice emit aliases:
- `x1` may be `BTN_SIDE` **or** `BTN_BACK`
- `x2` may be `BTN_EXTRA` **or** `BTN_FORWARD`

Listener must support both sets in evdev path.

Current expected behavior in code:
- `x1 -> {BTN_SIDE, BTN_BACK}`
- `x2 -> {BTN_EXTRA, BTN_FORWARD}`

If missing, patch `vibemouse/mouse_listener.py` accordingly and add tests.

---

## 6) Restart + final verification

```bash
systemctl --user daemon-reload
systemctl --user restart vibemouse.service
systemctl --user is-active vibemouse.service
vibemouse doctor
```

Functional smoke expectations:
1. front button toggles recording
2. rear button sends Enter (idle) / stops recording (recording)
3. hold right button + swipe left/right switches workspace

If still flaky, add temporary runtime logs in listener dispatch path:
- received event code
- resolved button label
- classified gesture direction
- resolved action
