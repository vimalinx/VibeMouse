# VibeMouse

面向 VibeCoding 的鼠标侧键语音输入工具。

English README: [`README.md`](./README.md)

AI 适配指南：
- English: [`docs/AI_ASSISTANT_DEPLOYMENT.md`](./docs/AI_ASSISTANT_DEPLOYMENT.md)
- 中文：[`docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md`](./docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md)
- AI 调试 Runbook：[`docs/AI_DEBUG_RUNBOOK.md`](./docs/AI_DEBUG_RUNBOOK.md)

## 这个项目解决什么问题

VibeMouse 把高频语音工作流绑定到鼠标侧键：
- 前侧键：开始 / 结束录音
- 空闲态按后侧键：发送 Enter
- 录音态按后侧键：停止录音并把转写发送到 OpenClaw

核心目标是低摩擦、可日常稳定使用，并且每个环节失败时都有回退路径。

## 运行架构（核心）

整体是事件驱动，按职责拆分：

1. `vibemouse/main.py`
   - CLI 入口（`run` / `doctor`）
2. `vibemouse/app.py`
   - 编排按钮事件、录音状态、转写线程和输出路由
3. `vibemouse/mouse_listener.py`
   - 监听侧键与手势（优先 `evdev`，含回退）
4. `vibemouse/audio.py`
   - 录音并写入临时 WAV
5. `vibemouse/transcriber.py`
   - SenseVoice 后端选择与识别
6. `vibemouse/output.py`
   - 输入 / 剪贴板 / OpenClaw 路由与失败回退
7. `vibemouse/system_integration.py`
   - 平台适配边界（当前 Hyprland，可扩展 Windows/macOS）
8. `vibemouse/doctor.py`
   - 内置自检（环境、OpenClaw、输入权限、冲突绑定）

## 快速开始（Linux）

### Ubuntu / Debian 依赖

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-atspi-2.0 portaudio19-dev libsndfile1
```

### Arch 依赖

```bash
sudo pacman -Syu --needed python python-pip python-gobject portaudio libsndfile
```

### 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

### 运行

```bash
export VIBEMOUSE_BACKEND=funasr_onnx
export VIBEMOUSE_DEVICE=cpu
vibemouse
```

默认安装走 ONNX 优先，部署体积更小。

- 可选 PyTorch 后端（GPU/高级兜底）：`pip install -e ".[pt]"`
- 可选 Intel NPU 依赖：`pip install -e ".[npu]"`

### 一键自动部署（推荐）

```bash
bash scripts/auto-deploy.sh --preset stable
```

这个命令会自动完成 `.venv` 初始化、安装 VibeMouse、生成 service/env 文件、
启用 `systemd --user` 服务并执行 `vibemouse doctor`。

可选预设：
- `stable`：日常稳定均衡
- `fast`：更低去抖 + 更高 OpenClaw 重试
- `low-resource`：更低后台资源占用

示例：

```bash
# 稳定档
bash scripts/auto-deploy.sh --preset stable

# 低资源档
bash scripts/auto-deploy.sh --preset low-resource

# 指定你自己的 OpenClaw 助手
bash scripts/auto-deploy.sh --preset stable --openclaw-agent ops
```

## 默认映射与状态逻辑

- `VIBEMOUSE_FRONT_BUTTON` 默认：`x1`
- `VIBEMOUSE_REAR_BUTTON` 默认：`x2`

状态矩阵：
- 空闲 + 后侧键 -> Enter（由 `VIBEMOUSE_ENTER_MODE` 控制）
- 录音中 + 后侧键 -> 停止录音 + OpenClaw 路由

如果鼠标物理定义相反：

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
```

## OpenClaw 集成（核心）

OpenClaw 路由可配置：
- `VIBEMOUSE_OPENCLAW_COMMAND`（默认 `openclaw`）
- `VIBEMOUSE_OPENCLAW_AGENT`（默认 `main`）
- `VIBEMOUSE_OPENCLAW_TIMEOUT_S`（默认 `20.0`）
- `VIBEMOUSE_OPENCLAW_RETRIES`（默认 `0`）

调度行为：
- 快速非阻塞派发，避免阻塞交互
- 返回路由原因（如 `dispatched`、`dispatched_after_retry_*`、`spawn_error:*`）
- 命令无效或拉起失败时自动回退到剪贴板

部署提示：如果你用自己的本地 AI 助手体系，把
`VIBEMOUSE_OPENCLAW_AGENT` 改成你自己的助手 ID。

## 内置自检 Doctor

运行：

```bash
vibemouse doctor
```

先执行安全自动修复再复检：

```bash
vibemouse doctor --fix
```

当前检查项：
- 配置加载是否有效
- OpenClaw 命令是否可执行 + agent 是否存在
- 麦克风输入设备可用性
- Linux 输入设备权限 / 侧键能力
- Hyprland 后侧键 Return 冲突绑定
- `systemctl --user` 服务状态

当前 `--fix` 自动修复项：
- 自动禁用冲突的 Hyprland 侧键 Return 绑定
- 尝试拉起处于 inactive 状态的 `vibemouse.service`

只要存在 `FAIL`，命令退出码就是非零，方便自动化检测。

## Deploy 命令

也可以直接用 deploy 子命令：

```bash
vibemouse deploy --preset stable
```

常用参数：
- `--preset stable|fast|low-resource`
- `--openclaw-command "openclaw --profile prod"`
- `--openclaw-agent main`
- `--openclaw-retries 2`
- `--log-file ~/.local/state/vibemouse/service.log`
- `--skip-systemctl`
- `--dry-run`

建议开启持久化调试日志：

```bash
tail -f ~/.local/state/vibemouse/service.log
```

## 常用配置项

| 变量 | 默认值 | 作用 |
|---|---|---|
| `VIBEMOUSE_ENTER_MODE` | `enter` | 后侧键提交模式（`enter`、`ctrl_enter`、`shift_enter`、`none`） |
| `VIBEMOUSE_AUTO_PASTE` | `false` | 回退到剪贴板后是否自动粘贴 |
| `VIBEMOUSE_GESTURES_ENABLED` | `false` | 是否启用手势识别 |
| `VIBEMOUSE_GESTURE_TRIGGER_BUTTON` | `rear` | 手势触发键（`front`、`rear`、`right`） |
| `VIBEMOUSE_GESTURE_THRESHOLD_PX` | `120` | 手势识别阈值 |
| `VIBEMOUSE_GESTURE_FREEZE_POINTER` | `true` | 手势期间是否冻结指针 |
| `VIBEMOUSE_PREWARM_ON_START` | `true` | 启动预热，降低首次识别延迟 |
| `VIBEMOUSE_PREWARM_DELAY_S` | `0.0` | 启动后延迟执行 ASR 预热，改善初始响应速度 |
| `VIBEMOUSE_STATUS_FILE` | `$XDG_RUNTIME_DIR/vibemouse-status.json` | 运行状态文件（状态栏读取） |

完整配置以 `vibemouse/config.py` 为准。

## 故障排查（短版）

### 事故复盘："录音/手势/回车一起失灵"

当你遇到“录音、右键手势、回车都失灵”时，最常见根因并不是服务挂掉，
而是**鼠标侧键底层事件码不匹配**。

典型现象：
- `vibemouse.service` 显示 `active`
- `hyprctl dispatch workspace e-1/e+1` 手动执行是 `ok`
- 但侧键触发不到任何动作，体感像“全炸了”

我们实战遇到的真实根因：
1. 监听器只匹配了 `BTN_SIDE` / `BTN_EXTRA`
2. 部分鼠标实际会报 `BTN_BACK` / `BTN_FORWARD`
3. 配置本身正确，但监听层没识别到原始按键事件

当前代码修复：
- `x1` 同时匹配 `{BTN_SIDE, BTN_BACK}`
- `x2` 同时匹配 `{BTN_EXTRA, BTN_FORWARD}`

建议排查顺序（最快）：
1. `systemctl --user is-active vibemouse.service`
2. 手动执行 `hyprctl dispatch workspace e-1` 与 `e+1`
3. `vibemouse doctor`
4. 从 `/proc/<MainPID>/environ` 确认运行时变量：
   - `VIBEMOUSE_GESTURE_TRIGGER_BUTTON`
   - `VIBEMOUSE_GESTURE_LEFT_ACTION`
   - `VIBEMOUSE_GESTURE_RIGHT_ACTION`
   - `VIBEMOUSE_FRONT_BUTTON` / `VIBEMOUSE_REAR_BUTTON`

如果前 1~3 项都通过但按钮仍无动作，请优先排查监听器事件兼容路径。

### 录音时后侧键仍然发送回车

检查并移除 Hyprland 的硬绑定：

```ini
bind = , mouse:275, sendshortcut, , Return, activewindow
bind = , mouse:276, sendshortcut, , Return, activewindow
```

然后重载：

```bash
hyprctl reload config-only
```

### OpenClaw 路由异常

```bash
openclaw agent --agent main --message "ping" --json
vibemouse doctor
```

### Linux 下侧键监听不到

```bash
sudo usermod -aG input $USER
# 需要重新登录
```

## 给 AI 助手做平台适配

请直接看这两份专用指南：

- [`docs/AI_ASSISTANT_DEPLOYMENT.md`](./docs/AI_ASSISTANT_DEPLOYMENT.md)
- [`docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md`](./docs/AI_ASSISTANT_DEPLOYMENT.zh-CN.md)
- [`docs/AI_DEBUG_RUNBOOK.md`](./docs/AI_DEBUG_RUNBOOK.md)

里面包含：架构契约、依赖下载地址、平台适配流程、以及可直接复用的 AI 提示模板。

## License

项目源码采用 Apache-2.0，详见 `LICENSE`。

第三方依赖与模型资产声明见 `THIRD_PARTY_NOTICES.md`。
