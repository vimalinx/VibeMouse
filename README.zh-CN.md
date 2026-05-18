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
- 录音态按后侧键：停止录音并通过默认文本通路输出转写

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
   - 输入 / 剪贴板输出与失败回退
7. `vibemouse/system_integration.py`
   - 平台适配边界（当前 Hyprland，可扩展 Windows/macOS）
8. `vibemouse/doctor.py`
   - 内置自检（环境、输入权限、冲突绑定）

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
- 可选本地 Opus-MT 翻译依赖：`pip install -e ".[translation]"`
- 可选 Intel NPU 依赖：`pip install -e ".[npu]"`

## 转写档位与个人词典

VibeMouse 现在对外只暴露两种用户可理解的转写档位，而不是直接暴露底层模型名：
- `Fast`：低延迟、适合日常常驻，走当前 SenseVoice 路径
- `Enhanced`：准确率优先，把加权热词传给 FunASR 后端

档位按输出目标分别配置：
- `default`

个人词典条目结构如下：

```json
{
  "term": "Codex",
  "phrases": ["codex", "code x", "扣带思"],
  "weight": 8,
  "scope": "both",
  "enabled": true
}
```

行为规则：
- `Enhanced` 会把 `phrases` 和 `weight` 作为解码热词偏置
- `Fast` 和 `Enhanced` 都会在转写后把命中的短语规范化回 `term`
- `scope` 可选 `default` 或 `both`
- 如果 `Enhanced` 当前不可用，运行时会明确报错，不会偷偷降级

完整示例可参考 [`shared/examples/config.example.json`](./shared/examples/config.example.json)。

## 本地设置界面

启动本地设置页：

```bash
vibemouse settings --open-browser
```

如果不想自动打开浏览器：

```bash
vibemouse settings
```

这个界面可以：
- 切换默认转写档位的 `Fast` / `Enhanced`
- 增删改查词典条目，并启用或禁用
- 查看后端可用性与依赖缺失原因

## 转写评测脚本

如果你想拿自己的录音真实比对不同档位，可以先按
[`shared/examples/dictation_eval.jsonl`](./shared/examples/dictation_eval.jsonl)
准备 JSONL 样例，然后运行：

```bash
python scripts/eval_dictation_profiles.py \
  --dataset shared/examples/dictation_eval.jsonl \
  --profile fast \
  --profile enhanced
```

脚本会输出：
- 文本完全匹配率
- 词典术语命中率
- 后端可用性与不可用原因

示例文件里的音频路径只是占位符，真正运行前要替换成你本地的 WAV 文件路径。

### 一键自动部署（推荐）

```bash
bash scripts/auto-deploy.sh --preset stable
```

这个命令会自动完成 `.venv` 初始化、安装 VibeMouse、生成 service/env 文件、
启用 `systemd --user` 服务并执行 `vibemouse doctor`。

可选预设：
- `stable`：日常稳定均衡
- `fast`：更低去抖，侧键响应更快
- `low-resource`：更低后台资源占用

示例：

```bash
# 稳定档
bash scripts/auto-deploy.sh --preset stable

# 低资源档
bash scripts/auto-deploy.sh --preset low-resource
```

## 默认映射与状态逻辑

- `VIBEMOUSE_FRONT_BUTTON` 默认：`x1`
- `VIBEMOUSE_REAR_BUTTON` 默认：`x2`

状态矩阵：
- 空闲 + 后侧键 -> Enter（由 `VIBEMOUSE_ENTER_MODE` 控制）
- 录音中 + 后侧键 -> 停止录音 + 默认文本输出

如果鼠标物理定义相反：

```bash
export VIBEMOUSE_FRONT_BUTTON=x2
export VIBEMOUSE_REAR_BUTTON=x1
```

## 运行时设置重载

本地设置页保存配置后，会请求正在运行的 daemon 重载配置。
如果你需要给本地命令服务增加鉴权，可设置：
- `VIBEMOUSE_COMMAND_AUTH_TOKEN`
- `config.json` 里的 `runtime.command_auth_token`

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
- `--command-auth-token reload-secret`
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
| `VIBEMOUSE_COMMAND_AUTH_TOKEN` | 未设置 | 本地命令服务客户端的可选鉴权 token |

完整配置以 `vibemouse/config/schema.py` 为准。

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

### 设置页改动没有应用到运行中的 daemon

```bash
cat "${XDG_RUNTIME_DIR:-/tmp}/vibemouse-status.json"
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
