# VibeMouse

**一个面向 VibeCoding 的 Linux 鼠标侧键语音输入工具。**

English README: [`README.md`](./README.md)

VibeMouse 把鼠标侧键变成高频编码工作流：

- 🎙️ 按侧键开始/结束录音
- ✍️ 自动语音转文字（SenseVoice）
- ⌨️ 有输入框就直接输入，没有就写入剪贴板
- ↩️ 后侧键发送 Enter（录音中改为发送到 OpenClaw）

如果你经常在 ChatGPT / Claude / IDE 里写提示词或代码，这个工具可以让你更少离开鼠标。

---

## 为什么是 VibeMouse？

VibeCoding 的典型动作是：

1. 想
2. 说
3. 提交

VibeMouse 把这三步绑定到鼠标侧键，减少键盘鼠标来回切换。

---

## 功能

- 全局监听鼠标侧键
- 一个侧键控制录音开始/结束
- 使用 SenseVoice 做语音识别
- 智能输出策略：
  - 焦点在可编辑输入框：直接键入
  - 焦点不在可编辑输入框：复制到剪贴板（可开启自动粘贴）
- 后侧键按状态分流：
  - 空闲：发送 Enter
  - 录音中：停止录音并把转写内容发给 OpenClaw
- 默认 CPU 稳定模式（开箱可用）
- 可切换识别后端（`funasr` / `funasr_onnx`）

---

## 当前支持平台

- Linux
- Python 3.10+

---

## 快速开始

### 1）安装系统依赖（Ubuntu/Debian）

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-atspi-2.0 portaudio19-dev libsndfile1
```

### 2）安装项目

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### 3）运行（推荐稳定模式）

```bash
export VIBEMOUSE_BACKEND=auto
export VIBEMOUSE_DEVICE=cpu
vibemouse
```

---

## 默认按键映射

- `x1` → 语音键（开始/结束录音）
- `x2` → Enter（空闲）/ OpenClaw 提交（录音中）

如果你的鼠标反过来：

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
vibemouse
```

---

## 工作流程

1. 按一次语音键，开始录音
2. 再按一次语音键，停止录音并识别
3. 如果当前焦点可编辑，自动输入文字
4. 否则自动复制到剪贴板
5. 按后侧键：
   - 空闲态发送 Enter
   - 录音态停止录音并发送到 OpenClaw

---

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VIBEMOUSE_BACKEND` | `auto` | `auto` / `funasr` / `funasr_onnx` |
| `VIBEMOUSE_MODEL` | `iic/SenseVoiceSmall` | 模型 ID 或路径 |
| `VIBEMOUSE_DEVICE` | `cpu` | 设备偏好（`cpu`、`cuda:0`、`npu:0`） |
| `VIBEMOUSE_FALLBACK_CPU` | `true` | 首选设备失败时是否回退 CPU |
| `VIBEMOUSE_BUTTON_DEBOUNCE_MS` | `150` | 侧键去抖窗口（毫秒），窗口内重复触发会被忽略 |
| `VIBEMOUSE_GESTURES_ENABLED` | `false` | 是否启用侧键鼠标手势识别 |
| `VIBEMOUSE_GESTURE_TRIGGER_BUTTON` | `rear` | 手势触发键（`front`、`rear` 或 `right`） |
| `VIBEMOUSE_GESTURE_THRESHOLD_PX` | `120` | 识别为手势所需的最小移动距离 |
| `VIBEMOUSE_GESTURE_FREEZE_POINTER` | `true` | 手势期间独占鼠标设备，减少光标漂移 |
| `VIBEMOUSE_GESTURE_RESTORE_CURSOR` | `true` | 手势动作触发后恢复光标位置 |
| `VIBEMOUSE_GESTURE_UP_ACTION` | `record_toggle` | `up` 手势动作：`record_toggle`、`send_enter`、`workspace_left`、`workspace_right`、`noop` |
| `VIBEMOUSE_GESTURE_DOWN_ACTION` | `noop` | `down` 手势动作：`record_toggle`、`send_enter`、`workspace_left`、`workspace_right`、`noop` |
| `VIBEMOUSE_GESTURE_LEFT_ACTION` | `noop` | `left` 手势动作：`record_toggle`、`send_enter`、`workspace_left`、`workspace_right`、`noop` |
| `VIBEMOUSE_GESTURE_RIGHT_ACTION` | `send_enter` | `right` 手势动作：`record_toggle`、`send_enter`、`workspace_left`、`workspace_right`、`noop` |
| `VIBEMOUSE_ENTER_MODE` | `enter` | 后侧键提交模式：`enter`、`ctrl_enter`、`shift_enter`、`none` |
| `VIBEMOUSE_AUTO_PASTE` | `false` | 回退到剪贴板时自动发送 `Ctrl+V` 粘贴 |
| `VIBEMOUSE_OPENCLAW_COMMAND` | `openclaw` | OpenClaw CLI 命令前缀，例如 `openclaw --profile prod` |
| `VIBEMOUSE_OPENCLAW_AGENT` | `main` | 目标 agent，运行时追加 `--agent`（部署时可改成你自己的本地 AI 助手 ID） |
| `VIBEMOUSE_OPENCLAW_TIMEOUT_S` | `20.0` | 执行 `openclaw agent` 的超时时间（秒） |
| `VIBEMOUSE_TRUST_REMOTE_CODE` | `false` | 仅在可信模型明确要求远端代码时设为 `true` |
| `VIBEMOUSE_PREWARM_ON_START` | `true` | 启动时预热 ASR 后端，缩短首次识别等待时间 |
| `VIBEMOUSE_STATUS_FILE` | `$XDG_RUNTIME_DIR/vibemouse-status.json` | 供顶栏读取的运行状态文件 |
| `VIBEMOUSE_LANGUAGE` | `auto` | `auto`、`zh`、`en`、`yue`、`ja`、`ko` |
| `VIBEMOUSE_USE_ITN` | `true` | 是否开启文本归一化 |
| `VIBEMOUSE_ENABLE_VAD` | `true` | 是否开启 VAD |
| `VIBEMOUSE_VAD_MAX_SEGMENT_MS` | `30000` | VAD 单段最大时长（毫秒） |
| `VIBEMOUSE_MERGE_VAD` | `true` | 是否合并 VAD 分段 |
| `VIBEMOUSE_MERGE_LENGTH_S` | `15` | VAD 合并阈值（秒） |
| `VIBEMOUSE_SAMPLE_RATE` | `16000` | 录音采样率 |
| `VIBEMOUSE_CHANNELS` | `1` | 录音声道 |
| `VIBEMOUSE_DTYPE` | `float32` | 录音数据类型 |
| `VIBEMOUSE_FRONT_BUTTON` | `x1` | 语音侧键（`x1` / `x2`） |
| `VIBEMOUSE_REAR_BUTTON` | `x2` | Enter 侧键（`x1` / `x2`） |
| `VIBEMOUSE_TEMP_DIR` | 系统临时目录 | 临时音频目录 |

---

## 常见问题

### 侧键监听不到

通常是 Linux 输入设备权限问题。把用户加到 `input` 组并重新登录：

```bash
sudo usermod -aG input $USER
```

### 识别结果没有直接输入到目标应用

有些应用没有暴露标准可编辑可访问性元数据，此时会按设计回退到剪贴板。

在 Hyprland 下，终端窗口（foot/kitty/alacritty/wezterm 等）会自动使用更适合终端的粘贴快捷键（优先 `Ctrl+Shift+V`，失败回退 `Shift+Insert`）。

### 后侧键回车不稳定

可切换提交组合键并加大去抖：

```bash
export VIBEMOUSE_ENTER_MODE=ctrl_enter
export VIBEMOUSE_BUTTON_DEBOUNCE_MS=220
systemctl --user restart vibemouse.service
```

如果你使用 Hyprland，也可以把回车改成合成器级绑定，并关闭 VibeMouse 的后侧键回车：

```ini
# ~/.config/hypr/UserConfigs/UserKeybinds.conf
bind = , mouse:276, sendshortcut, , Return, activewindow
# 如果你的物理后侧键是 X1，请改成 mouse:275
```

```bash
export VIBEMOUSE_ENTER_MODE=none
systemctl --user restart vibemouse.service
hyprctl reload config-only
```

### 录音中按后侧键没有发送到 OpenClaw

先确认 OpenClaw CLI 可用：

```bash
openclaw agent --message "ping" --json
```

如果你使用自定义路径或 profile：

```bash
export VIBEMOUSE_OPENCLAW_COMMAND="openclaw --profile prod"
export VIBEMOUSE_OPENCLAW_AGENT="ops"
systemctl --user restart vibemouse.service
```

部署提示：如果你本地有多个 AI 助手，可以把 `VIBEMOUSE_OPENCLAW_AGENT`
改成你自己的助手 ID（例如 `main`、`ops` 或自定义 agent 名称）。

### 鼠标手势没有触发动作

请先开启手势并指定触发键：

```bash
export VIBEMOUSE_GESTURES_ENABLED=true
export VIBEMOUSE_GESTURE_TRIGGER_BUTTON=rear
export VIBEMOUSE_GESTURE_THRESHOLD_PX=120
systemctl --user restart vibemouse.service
```

默认手势映射为：

- `up` -> 切换录音（开始/停止）
- `right` -> 发送 Enter
- `down` / `left` -> 无动作

你可以通过 `VIBEMOUSE_GESTURE_*_ACTION` 重映射各方向动作。

如果按住触发键时仍有明显光标漂移，请保持
`VIBEMOUSE_GESTURE_FREEZE_POINTER=true`（默认值）。在 Hyprland + Arch 这类
可用 evdev 的环境下，它会在手势期间独占鼠标设备来降低漂移。

### Hyprland 右键手势切换桌面

如果你希望“按住右键后左右滑动”来切换工作区：

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

### 启动后或长时间空闲后首次识别较慢

可开启启动预热，让 ASR 后端在首次说话前先加载：

```bash
export VIBEMOUSE_PREWARM_ON_START=true
systemctl --user restart vibemouse.service
```

可用以下命令确认预热日志：

```bash
journalctl --user -u vibemouse.service -n 30 --no-pager | rg "prewarm"
```

### 能录音但识别为空

优先检查麦克风增益/输入源，确认录到的不是静音。

---

## NPU / OpenVINO 说明

NPU 是否可用，取决于模型图是否能被 NPU 编译器接受。

本项目默认 CPU 是刻意选择：优先稳定可用。即使 NPU 编译失败，也会保持 CPU 回退，确保流程不中断。

---

## 后台常驻运行（可选）

你可以用 tmux/screen/systemd 让它常驻。

示例（tmux）：

```bash
tmux new -d -s vibemouse "source .venv/bin/activate && vibemouse"
tmux attach -t vibemouse
```

---

## 项目结构

```text
vibemouse/
  app.py            # 主流程编排
  audio.py          # 录音
  mouse_listener.py # 侧键监听
  transcriber.py    # 识别后端
  output.py         # 输入/剪贴板/回车输出
  config.py         # 环境变量配置
  main.py           # 入口
```

---

## 开发检查

```bash
python -m compileall vibemouse
python -m pip check
```

---

## License

VibeMouse 项目源码采用 Apache-2.0 许可证，详见 `LICENSE`。

第三方依赖与模型资产声明见 `THIRD_PARTY_NOTICES.md`。

在分发二进制或打包模型前，请重点复核 LGPL 依赖（`pynput`、`PyGObject`）
的合规要求，并确认你实际使用的模型 ID 对应许可证。
