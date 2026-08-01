---
title: "VibeMouse v0.2.2：一条命令部署，自带医生看病"
date: 2026-03-07
type: update
cover: images/cover.jpg
tags: [vibemouse, release, v0.2.2, 更新日志]
author: "vimalinx"
---

v0.2.2 发布了 🎉 这一周密集的更新，全部围绕一个目标：**装得上、跑得稳、坏了能自己查**。

**✨ 一键部署**

```bash
bash scripts/auto-deploy.sh --preset stable
```

自动建 venv、装包、生成 systemd --user 服务、跑诊断。
三档预设可选：

- `stable`：日常主力默认
- `fast`：更低防抖 + 更高 OpenClaw 重试
- `low-resource`：更低后台占用

**🩺 内置 doctor 诊断**

```bash
vibemouse doctor        # 检查
vibemouse doctor --fix  # 先自动修再复查
```

检查项包括：配置有效性、OpenClaw 命令与 agent、麦克风、
input 设备权限、Hyprland 按键冲突、systemd 服务状态。
`--fix` 能自动禁用冲突的 Hyprland 侧键 Return 绑定、重启挂掉的服务。

**🔧 稳定性修复（都是真实踩过的坑）**

- 修复 USB 热插拔后鼠标监听器挂掉的问题
- 修复热插拔后右键手势失效
- 修复终端自动粘贴的可靠性，服务日志持久化到
  `~/.local/state/vibemouse/service.log`
- 新增键盘录音热键，和鼠标触发并行可用
- 默认后端切到 ONNX，PyTorch 变成可选 extras

**📖 文档**

中英双语 README 重写，新增 AI 助手部署指南
（`docs/AI_ASSISTANT_DEPLOYMENT.md`），
方便让 AI 帮你把这套东西适配到自己的环境。

完整提交记录见 git log，下周继续肝 💪
