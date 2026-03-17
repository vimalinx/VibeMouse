# IPC Integration

VibeMouse exposes two IPC paths:

- Built-in `agent <-> listener` transport: `stdio + LPJSON`
- External control transport: stable local endpoint for command-only clients

The message schema is defined in [`shared/schema/ipc.schema.json`](../shared/schema/ipc.schema.json).

## External Command Endpoint

External programs should connect to the stable local endpoint exposed by the agent:

- Windows: `\\.\pipe\vibemouse`
- Linux/macOS: `${XDG_RUNTIME_DIR:-temp}/vibemouse.sock`

The current endpoint is also written to `status.json` as `ipc_socket`.

Notes:

- External clients should send `command` messages only.
- External clients should not send `event` messages.
- The built-in listener path still uses `stdio`; it does not use the external endpoint.

## Framing

All IPC messages use LPJSON:

1. 4-byte little-endian unsigned length prefix
2. UTF-8 JSON payload

Example payload:

```json
{"type":"command","command":"toggle_recording"}
```

## Message Types

Two message shapes are supported:

### Command Message

```json
{"type":"command","command":"shutdown"}
```

### Event Message

```json
{"type":"event","event":"mouse.side_front.press"}
```

`event` messages are intended for the listener-to-agent path. External integrations should generally use `command`.

## Supported Commands

| Command | Description |
|---|---|
| `noop` | No operation; event is ignored |
| `toggle_recording` | Start or stop voice recording |
| `trigger_secondary_action` | In idle: send Enter. In recording: stop and send transcript to OpenClaw |
| `submit_recording` | Stop recording and send transcript to OpenClaw |
| `send_enter` | Send Enter key to the focused input |
| `workspace_left` | Switch workspace left |
| `workspace_right` | Switch workspace right |
| `reload_config` | Reload `config.json` |
| `shutdown` | Gracefully shut down the agent |

Canonical source: [`shared/protocol/COMMANDS.md`](../shared/protocol/COMMANDS.md)

## Supported Events

| Event | Description |
|---|---|
| `mouse.side_front.press` | Front side button press |
| `mouse.side_rear.press` | Rear side button press |
| `hotkey.record_toggle` | Recording toggle hotkey |
| `hotkey.recording_submit` | Recording submit hotkey |
| `gesture.up` | Upward gesture |
| `gesture.down` | Downward gesture |
| `gesture.left` | Leftward gesture |
| `gesture.right` | Rightward gesture |

Canonical source: [`shared/protocol/EVENTS.md`](../shared/protocol/EVENTS.md)

## Client Examples

### Python: Unix Socket

```python
import json
import socket
import struct

endpoint = "/tmp/vibemouse.sock"
payload = {"type": "command", "command": "toggle_recording"}
body = json.dumps(payload).encode("utf-8")
frame = struct.pack("<I", len(body)) + body

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
    conn.connect(endpoint)
    conn.sendall(frame)
```

### Python: Windows Named Pipe

```python
import json
import struct

endpoint = r"\\.\pipe\vibemouse"
payload = {"type": "command", "command": "toggle_recording"}
body = json.dumps(payload).encode("utf-8")
frame = struct.pack("<I", len(body)) + body

with open(endpoint, "r+b", buffering=0) as pipe:
    pipe.write(frame)
```

## Runtime Discovery

If you do not want to hardcode the endpoint, read `status.json` and inspect:

- `ipc_socket`: stable local endpoint
- `listener_mode`: `inline`, `child`, or `off`
- `state`: `idle`, `recording`, or `processing`

Default status file path is platform/runtime dependent and configured by `runtime.status_file`.
