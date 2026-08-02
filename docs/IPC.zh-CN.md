# IPC 集成说明

VibeMouse 当前有两条 IPC 通路：

- 内建 `agent <-> listener`：`stdio + LPJSON`
- 外部控制通道：面向第三方程序的稳定本地 endpoint，仅接收命令

消息 schema 定义见 [`shared/schema/ipc.schema.json`](../shared/schema/ipc.schema.json)。

## 外部命令通道地址

外部程序集成时，应该连接 agent 暴露出来的稳定本地地址：

- Windows: `\\.\pipe\vibemouse`
- Linux/macOS: `${XDG_RUNTIME_DIR:-temp}/vibemouse.sock`

agent 也会把当前地址写入 `status.json` 的 `ipc_socket` 字段。

注意：

- 外部客户端应只发送 `command` 消息
- 外部客户端不应发送 `event` 消息
- 内建 listener 链路仍然走 `stdio`，不会走这个外部 endpoint

## 帧格式

所有 IPC 消息都使用 LPJSON：

1. 前 4 字节：小端无符号整数，表示后续 JSON 长度
2. 后续内容：UTF-8 JSON payload

示例：

```json
{"type":"command","command":"toggle_recording"}
```

## 消息类型

支持两种消息结构：

### Command Message

```json
{"type":"command","command":"shutdown"}
```

### Event Message

```json
{"type":"event","event":"mouse.side_front.press"}
```

`event` 主要用于 listener -> agent。外部集成一般只需要发送 `command`。

## 当前支持的命令

| Command | 说明 |
|---|---|
| `noop` | 空操作 |
| `toggle_recording` | 开始或停止录音 |
| `trigger_secondary_action` | 空闲时发送 Enter，录音时停止并提交到 OpenClaw |
| `submit_recording` | 停止录音并提交到 OpenClaw |
| `send_enter` | 向当前焦点输入框发送 Enter |
| `workspace_left` | 切换到左侧工作区 |
| `workspace_right` | 切换到右侧工作区 |
| `reload_config` | 重新加载 `config.json` |
| `shutdown` | 优雅关闭 agent |

规范来源：[`shared/protocol/COMMANDS.md`](../shared/protocol/COMMANDS.md)

## 当前支持的事件

| Event | 说明 |
|---|---|
| `mouse.side_front.press` | 前侧键按下 |
| `mouse.side_rear.press` | 后侧键按下 |
| `hotkey.record_toggle` | 录音切换热键 |
| `hotkey.recording_submit` | 录音提交热键 |
| `gesture.up` | 上手势 |
| `gesture.down` | 下手势 |
| `gesture.left` | 左手势 |
| `gesture.right` | 右手势 |

规范来源：[`shared/protocol/EVENTS.md`](../shared/protocol/EVENTS.md)

## 客户端示例

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

## 运行时发现方式

如果不想在客户端里硬编码地址，可以读取 `status.json`，关注这些字段：

- `ipc_socket`：稳定本地 IPC 地址
- `listener_mode`：`inline` / `child` / `off`
- `state`：`idle` / `recording` / `processing`

`status.json` 的默认路径由 `runtime.status_file` 决定。
