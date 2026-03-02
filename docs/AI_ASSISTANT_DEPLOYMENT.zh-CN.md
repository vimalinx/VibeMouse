# VibeMouse AI 助手部署与平台适配指南

本指南面向 AI 助手（以及使用 AI 助手的开发者），用于在新机器部署 VibeMouse，并安全地做新平台适配。

如果要做 Windows/macOS 适配，或者接入自定义桌面环境，请以本文件为执行基线。

## 1）项目目标与不可破坏行为

VibeMouse 是“鼠标侧键语音工作流”工具。

必须保持的行为：
- 前侧键：开始/结束录音
- 空闲态后侧键：发送 Enter
- 录音态后侧键：停止录音并将转写发送到 OpenClaw
- 任何失败都必须有可见回退，不能静默丢字

做适配时，禁止破坏上述状态机。

## 2）核心架构地图

关键模块：
- `vibemouse/main.py`：CLI 入口（`run`、`doctor`）
- `vibemouse/app.py`：主状态机、线程编排、输出路由
- `vibemouse/mouse_listener.py`：侧键监听与手势路径
- `vibemouse/audio.py`：录音
- `vibemouse/transcriber.py`：ASR 后端与识别
- `vibemouse/output.py`：输入/剪贴板/OpenClaw 路由与回退
- `vibemouse/system_integration.py`：平台适配边界
- `vibemouse/doctor.py`：部署与运行自检
- `vibemouse/config.py`：环境变量配置契约

## 3）平台适配边界（最重要）

适配新平台时，优先扩展 `vibemouse/system_integration.py`，不要把平台特化逻辑散落到 `app.py` / `output.py`。

运行时依赖的方法：
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

## 4）依赖项与下载地址

### 基础环境
- Python 3.10-3.12（当前建议 3.12；3.13+ 依赖链未稳定）：https://www.python.org/downloads/
- pip 安装文档：https://pip.pypa.io/en/stable/installation/

### 音频链路
- PortAudio：http://www.portaudio.com/download.html
- libsndfile：https://github.com/libsndfile/libsndfile
- `sounddevice`：https://pypi.org/project/sounddevice/
- `soundfile`：https://pypi.org/project/soundfile/

### 输入与桌面集成
- `pynput`：https://pypi.org/project/pynput/
- `evdev`（Linux）：https://python-evdev.readthedocs.io/en/latest/
- PyGObject / AT-SPI：https://pygobject.gnome.org/

### 语音识别与模型栈
- PyTorch：https://pypi.org/project/torch/
- Torchaudio：https://pypi.org/project/torchaudio/
- FunASR：https://pypi.org/project/funasr/
- FunASR ONNX：https://pypi.org/project/funasr-onnx/
- ONNX Runtime：https://pypi.org/project/onnxruntime/
- OpenVINO：https://pypi.org/project/openvino/
- ModelScope：https://pypi.org/project/modelscope/

### OpenClaw 目标
- OpenClaw 仓库：https://github.com/openclaw/openclaw

Python 依赖版本以 `pyproject.toml` 为准。

## 5）部署步骤（可直接让 AI 助手执行）

最快部署路径（推荐）：

```bash
bash scripts/auto-deploy.sh --preset stable
```

如果系统默认 `python3` 是 3.13+，脚本会自动尝试 `python3.12`。
也可以手工指定解释器：

```bash
VIBEMOUSE_PYTHON_BIN=python3.12 bash scripts/auto-deploy.sh --preset stable
```

预设可选：`stable`、`fast`、`low-resource`。

非 Linux（如 macOS/Windows）建议加 `--skip-systemctl`：

```bash
bash scripts/auto-deploy.sh --preset stable --skip-systemctl
```

也可以直接用 deploy 子命令：

```bash
vibemouse deploy --preset stable
```

1. 安装项目
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

2. 先跑自检
```bash
vibemouse doctor
vibemouse doctor --fix
```

3. 验证 OpenClaw
```bash
openclaw agent --agent main --message "ping" --json
```

4. 启动
```bash
vibemouse
```

首次启动说明：
- 可能会下载模型文件（约数百 MB 到约 1 GB），属于正常行为。
- macOS 需给终端开启“辅助功能”和“输入监控”权限，否则侧键监听不可用。

5. 手工验证状态矩阵
- 空闲态后侧键 -> Enter
- 录音态后侧键 -> OpenClaw 路由

## 6）Linux user service 部署

推荐 service 文件路径：
- `~/.config/systemd/user/vibemouse.service`

基础命令：
```bash
systemctl --user daemon-reload
systemctl --user enable --now vibemouse.service
systemctl --user status vibemouse.service
```

## 7）环境变量契约（关键）

OpenClaw：
- `VIBEMOUSE_OPENCLAW_COMMAND`
- `VIBEMOUSE_OPENCLAW_AGENT`
- `VIBEMOUSE_OPENCLAW_TIMEOUT_S`
- `VIBEMOUSE_OPENCLAW_RETRIES`

按钮与状态：
- `VIBEMOUSE_FRONT_BUTTON`
- `VIBEMOUSE_REAR_BUTTON`
- `VIBEMOUSE_ENTER_MODE`

识别性能：
- `VIBEMOUSE_BACKEND`
- `VIBEMOUSE_DEVICE`
- `VIBEMOUSE_PREWARM_ON_START`

手势：
- `VIBEMOUSE_GESTURES_ENABLED`
- `VIBEMOUSE_GESTURE_TRIGGER_BUTTON`
- `VIBEMOUSE_GESTURE_THRESHOLD_PX`
- `VIBEMOUSE_GESTURE_FREEZE_POINTER`

## 8）新平台适配检查单

新增 Windows/macOS 支持时：

1. 在 `system_integration.py` 增加平台类。
2. 用本地 API 实现快捷键发送、活动窗口检测、焦点探测。
3. 定义终端识别与粘贴策略。
4. 保留 `output.py` 的回退链路。
5. 保证 `app.py` 按键状态机不变。
6. 补充测试：
   - `tests/test_system_integration.py`
   - `tests/test_output.py`
   - `tests/test_app.py`
7. 跑完整验证：
```bash
python -m compileall vibemouse
python -m unittest discover -s tests -p "test_*.py"
vibemouse doctor
```

## 9）合并前回归门槛

- 前/后侧键状态语义不变
- OpenClaw 路由仍有失败回退
- doctor 输出对故障可读、可定位
- 全量测试通过，并补充平台测试
- Linux Hyprland 主路径不能退化

## 10）给 AI 助手的提示模板

可以直接把下面提示词交给 AI 助手：

```text
你要把 VibeMouse 适配到 <目标平台>。

约束：
1）必须保持按钮状态机：
   - 前侧键：开始/结束录音
   - 后侧键空闲态：Enter
   - 后侧键录音态：OpenClaw 路由
2）平台逻辑优先放在 system_integration.py，不要散落到其它模块。
3）必须保留失败回退（OpenClaw 启动失败回退到剪贴板）。
4）更新 test_system_integration.py、test_output.py、test_app.py。
5）执行 compileall + 全量单测 + vibemouse doctor，并报告结果。

交付：
- 代码改动
- 测试改动
- 验证证据
- 平台限制说明
```

这能保证适配过程可控、可测、可长期维护。
