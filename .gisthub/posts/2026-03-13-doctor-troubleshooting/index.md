---
title: "复盘：录音、手势、Enter 同时失灵，真凶竟不是服务挂了"
date: 2026-03-13
type: note
cover: images/cover.jpg
tags: [vibemouse, 排障, linux, evdev, 技术笔记]
author: "vimalinx"
---

分享一次真实 postmortem，README 里有完整记录 📝

**症状：**

用户反馈录音、右键手势、Enter 全部失灵。
服务明明是 `active`，手动跑 `hyprctl dispatch workspace` 也正常返回 ok。
体感就是「所有功能都坏了」。

**真凶：鼠标侧键事件码不匹配** 🎯

不是服务死了，是监听器根本不认识按键：

1. 代码最初只匹配 `BTN_SIDE` / `BTN_EXTRA`
2. 但有些鼠标发的是别名 `BTN_BACK` / `BTN_FORWARD`
3. 环境变量里映射配得再对，原始事件进不来也白搭

**修复（已进代码）：**

- `x1` 现在接受 `{BTN_SIDE, BTN_BACK}`
- `x2` 现在接受 `{BTN_EXTRA, BTN_FORWARD}`

**推荐的排查顺序（建议收藏）：**

1. `systemctl --user is-active vibemouse.service`
2. `hyprctl dispatch workspace e-1` / `e+1` 验证手势目标
3. `vibemouse doctor` 跑一遍诊断
4. 还不行就看 `/proc/<MainPID>/environ` 确认运行时环境变量
   （`VIBEMOUSE_FRONT_BUTTON` / `VIBEMOUSE_GESTURE_*` 等）

前三步都过但按键没反应？直接 debug 监听器的代码路径。

**另一个常见坑：**

录音中按后侧键还在发 Enter？
多半是 Hyprland 配置里有硬绑定冲突，检查
`~/.config/hypr/UserConfigs/UserKeybinds.conf` 里的
`bind = , mouse:275/276, sendshortcut, , Return, activewindow`，
删掉后 `hyprctl reload config-only`。

好消息是 `vibemouse doctor --fix` 现在能自动处理这类冲突了 ✅
