# VibeMouse 两步迁移方案

## 目标

本文档定义了 VibeMouse 从当前 Linux 优先、单 Python 包结构，迁移到目标版本的完整路线。

目标版本包含：

- Windows + macOS + Linux 三端适配
- `agent` 和 `panel` 拆分
- `panel` 作为配置面板，管理 JSON 配置
- `agent` 的核心运行时尽量完全跨平台一致
- `listener` 可被替换或独立关闭
- IPC 成为一等集成边界
- 单一版本线，按平台产出 release 资产

本方案刻意拆成两步：

- 第 1 步处理运行时边界和行为契约
- 第 2 步只处理最终 monorepo 包装

## 先回答：这些改动在第几步做

前面聊到的几项关键改动，**都属于第 1 步**，不是第 2 步：

- 把“前侧键/后侧键”这种具象输入改名为语义命令：**第 1 步**
- 把 `listener` 从 `agent` 里拆出来：**第 1 步**
- 引入“规范化输入事件 -> binding -> 语义命令”的链路：**第 1 步**
- 引入 agent 的 IPC 边界和运行模式（`listener=child` / `listener=off`）：**第 1 步**
- 在这些边界之上并回 Windows、补齐 macOS：**第 1 步**
- 把已经稳定的 Python 项目挪到 `agent/` 下：**第 2 步**

第 2 步不应该再重新定义运行时语义。第 2 步应该尽量只是目录搬迁和构建包装。

## 术语

- `agent`：常驻后台运行的主进程，负责 IPC、binding、状态机、录音、转写、输出路由、平台集成、doctor、deploy
- `listener`：原始输入监听组件，负责采集鼠标/键盘事件并产出规范化输入事件
- `panel`：配置和状态 UI，负责编辑 `config.json`、读取 `status.json`、触发有限控制动作
- `normalized input event`：设备无关的输入事件，例如 `mouse.side_front.press`
- `agent command`：语义化命令，例如 `toggle_recording`
- `config.json`：主配置文件，由 panel 管理
- `status.json`：运行状态文件，由 agent 管理

## 当前仓库状态

当前结构：

```text
VibeMouse/
  docs/
  scripts/
  tests/
  vibemouse/
    app.py
    audio.py
    config.py
    deploy.py
    doctor.py
    keyboard_listener.py
    logging_setup.py
    main.py
    mouse_listener.py
    output.py
    system_integration.py
    transcriber.py
  pyproject.toml
  README.md
```

当前特点：

- 运行时实际上聚焦 Linux + Hyprland
- 配置以环境变量为主
- 平台逻辑和核心运行时逻辑混在一起
- listener 相关职责和核心业务状态机耦合
- 输入语义还带有较强的设备/按键色彩
- `doctor` 和 `deploy` 明显偏 Linux
- 还没有稳定的 IPC 边界
- 还没有稳定的 `agent / listener / panel` 契约

## 目标架构

### 第 2 步完成后的最终结构

```text
VibeMouse/
  agent/
    pyproject.toml
    vibemouse/
      cli/
      core/
      config/
      platform/
      listener/
      bindings/
      ipc/
      ops/
    tests/
      cli/
      core/
      config/
      platform/
      listener/
      bindings/
      ipc/
      ops/
  panel/
  shared/
    schema/
      config.schema.json
      status.schema.json
      ipc.schema.json
    examples/
      config.example.json
    protocol/
      COMMANDS.md
      EVENTS.md
  docs/
  scripts/
```

### 目标运行链路

目标运行链路是：

```text
raw input
-> listener
-> normalized input event
-> agent IPC
-> binding resolver
-> semantic agent command
-> core state machine
```

外部系统也可以跳过 listener，直接经由 IPC 驱动 agent：

```text
external client
-> agent IPC
-> semantic agent command
-> core state machine
```

这会形成两种正式支持的运行模式：

- 默认模式：agent 启动并监管 listener 子进程
- `listener=off` 模式：agent 不启动 listener，只接受外部命令输入

## 核心设计决策

### 1. core agent 不再接收具象设备语义

core agent 不应该接收这些概念：

- `front_button_pressed`
- `rear_button_pressed`
- `BTN_SIDE`
- `mouse:275`

core agent 应该接收这些概念：

- `toggle_recording`
- `trigger_secondary_action`
- `workspace_left`
- `workspace_right`
- `reload_config`
- `shutdown`

### 2. 产品语义仍然留在共享 core

以下行为在三端必须一致：

- `toggle_recording` 负责切换录音状态机
- `trigger_secondary_action` 在空闲态发送 Enter
- `trigger_secondary_action` 在录音态结束录音并路由转写结果
- 文本输出 fallback 不能静默丢字

这些逻辑必须留在共享 core 里，不能散落到 listener 或平台后端。

### 3. listener 只产出规范化事件，不直接决定业务行为

listener 的职责：

- 全局鼠标 hook
- 全局键盘 hook
- 在确有必要时做贴近设备层的手势抽取
- 产出规范化输入事件

listener 不负责：

- 读取完整业务配置
- 维护核心状态机
- 决定最终业务行为

### 4. binding resolver 放在 agent 内部

binding 应当留在 agent 内部，而不是下沉到 listener：

- `config.json` 由 panel 管理，agent 统一读取更简单
- 配置迁移、热重载都集中在 agent
- 外部 IPC 客户端可以直接发 command，不必复刻 listener 逻辑
- listener 子进程会更轻、更可替换

### 5. IPC 是稳定的集成边界

IPC 至少需要承载：

- listener -> agent 的规范化输入事件
- 外部系统 -> agent 的语义命令
- panel -> agent 的管理命令
- agent -> 外部的状态/健康响应

### 6. 内建 IPC 传输方案固定为 `stdio + LPJSON`

对于内建的 `agent <-> listener` 路径，传输层固定为：

- `stdio`
- LPJSON，也就是长度前缀 JSON 消息

建议 framing：

- 4 字节小端无符号长度前缀
- UTF-8 JSON 负载
- 一帧对应一条逻辑消息

原因：

- Windows、macOS、Linux 三端都稳定支持
- 和受控子进程模型天然匹配
- 不需要端口分配，也不会碰防火墙
- Python、Node、Rust、Go 都容易实现

这个选择只针对内建 listener 子进程链路。

在第 1 步里，panel 不强制依赖持久 IPC server。它可以继续通过这些边界工作：

- `config.json`
- `status.json`
- 本地命令调用，用于 reload、restart、doctor 之类的有限动作

如果后续要增加外部控制传输层，也应该复用同一套 command schema，而不是重新定义命令语义。

## 操作改名与事件模型

### 改名规则

具象输入先变成规范化事件，再由 binding 映射成语义命令。

### 示例

| 旧的具象表述 | 规范化事件 | 语义命令 |
| --- | --- | --- |
| 前侧键 | `mouse.side_front.press` | `toggle_recording` |
| 后侧键 | `mouse.side_rear.press` | `trigger_secondary_action` |
| 录音热键 | `hotkey.record_toggle` | `toggle_recording` |
| 左手势 | `gesture.left` | `workspace_left` |
| 右手势 | `gesture.right` | `workspace_right` |

### 配置示例

```json
{
  "bindings": {
    "mouse.side_front.press": "toggle_recording",
    "mouse.side_rear.press": "trigger_secondary_action",
    "gesture.left": "workspace_left",
    "gesture.right": "workspace_right",
    "hotkey.record_toggle": "toggle_recording"
  }
}
```

## 为什么必须分两步

如果一次性做完，会把这些变化揉在一起：

- 三端适配
- 配置系统从 env 切到 JSON
- 输入模型重构
- listener / agent 拆分
- IPC 引入
- panel 引入
- Python 包内重构
- monorepo 包装
- CI / 发布流程重做

这会让回归风险过大。

两步路线的目的就是：

- 第 1 步先把运行时边界和契约稳定下来
- 第 2 步再把稳定后的结果搬进最终 monorepo 结构

## 第 1 步：在当前仓库内完成过渡整合

### 第 1 步目标

在不进入最终 monorepo 之前，先完成运行时架构的真正改造。这一步是行为和边界变化最重的一步。

### 第 1 步后的结构

```text
VibeMouse/
  panel/
  shared/
    schema/
    examples/
    protocol/
  vibemouse/
    cli/
    core/
    config/
    platform/
    listener/
    bindings/
    ipc/
    ops/
  tests/
    cli/
    core/
    config/
    platform/
    listener/
    bindings/
    ipc/
    ops/
  docs/
  scripts/
  pyproject.toml
```

### 第 1 步范围

#### A. 引入 JSON 配置与状态文件边界

把配置职责拆成：

- `schema.py`：配置结构、默认值、校验
- `store.py`：JSON 读写、原子写入
- `env_overrides.py`：环境变量覆盖
- `migration.py`：配置版本迁移

新增：

- `shared/schema/config.schema.json`
- `shared/schema/status.schema.json`
- `shared/examples/config.example.json`

所有权规则：

- panel 写 `config.json`
- agent 读 `config.json`
- agent 写 `status.json`
- panel 读 `status.json`

#### B. 引入语义命令

这一段就是“操作改名”真正落地的位置。

把核心内部能看到的命令改成语义化命令，例如：

- `toggle_recording`
- `trigger_secondary_action`
- `workspace_left`
- `workspace_right`
- `reload_config`
- `shutdown`

这部分属于 **第 1 步**，不属于第 2 步。

#### C. 把 listener 从 core agent 里拆出来

用这三层替代现在耦合的输入链路：

- `listener/`：原始采集与规范化
- `bindings/`：`event -> command`
- `core/`：状态机和业务行为

这部分也属于 **第 1 步**。

#### D. 引入 IPC 运行时边界

新增：

- `ipc/server.py`
- `ipc/client.py`
- `ipc/messages.py`
- `shared/schema/ipc.schema.json`
- `shared/protocol/COMMANDS.md`
- `shared/protocol/EVENTS.md`

必须支持的能力：

- listener 通过 IPC 向 agent 发送规范化事件
- panel 可以在不直接修改运行时内部对象的前提下触发有限管理动作
- 外部系统可以在 agent 进入附着控制模式时直接发送语义命令
- agent 可以选择是否监管 listener 子进程

内建链路的传输方案在这里固定：

- `agent <-> listener(child)` 采用 `stdio + LPJSON`

这里也是 `listener=off` 模式进入正式方案的位置。

#### E. 增加运行模式

建议命令形态：

- `vibemouse agent run --listener=child`
- `vibemouse agent run --listener=off`
- `vibemouse listener run --connect ...`

新命令（`vibemouse agent run`、`vibemouse listener run`）在同一 PR 内引入。现有 CLI 入口（`vibemouse run`、`vibemouse doctor`、`vibemouse deploy`）尽量保留，不强制删除；如果保留代价过高才可移除，移除须在引入新命令的同一 PR 内完成，不跨 PR 保留悬空路径。

#### F. 在这些边界之上并回三端平台实现

只有在 `core`、`listener`、`bindings`、`ipc` 这些层稳定之后，才做平台并回：

- 合并 `windows-port` 的 Windows 适配
- 按同样边界模型补齐 macOS
- Linux 继续作为回归基线

这个顺序很重要。平台适配应该建立在新边界之上，而不是先并平台、后拆结构。

#### G. 建立 panel 边界

第 1 步就创建 `panel/`，但职责要保持克制：

- 编辑 `config.json`
- 读取 `status.json`
- 打开配置目录和日志目录
- 发送有限控制命令，例如 reload、restart、doctor

panel 不负责：

- 输入监听
- 设备控制
- 音频采集
- 核心状态机

#### H. 重组测试和 CI

测试按职责拆分：

- `tests/cli/`
- `tests/core/`
- `tests/config/`
- `tests/platform/`
- `tests/listener/`
- `tests/bindings/`
- `tests/ipc/`
- `tests/ops/`

CI 改成三平台矩阵：

- Linux
- Windows
- macOS

### 第 1 步文件映射

当前文件到过渡结构的映射：

- `vibemouse/main.py` -> `vibemouse/cli/main.py`
- `vibemouse/app.py` -> `vibemouse/core/app.py`
- `vibemouse/audio.py` -> `vibemouse/core/audio.py`
- `vibemouse/output.py` -> `vibemouse/core/output.py`
- `vibemouse/transcriber.py` -> `vibemouse/core/transcriber.py`
- `vibemouse/logging_setup.py` -> `vibemouse/core/logging_setup.py`
- `vibemouse/config.py` -> 拆入 `vibemouse/config/`
- `vibemouse/system_integration.py` -> 拆入 `vibemouse/platform/`
- `vibemouse/mouse_listener.py` -> 拆入 `vibemouse/listener/`
- `vibemouse/keyboard_listener.py` -> 拆入 `vibemouse/listener/`
- 新增 `vibemouse/core/commands.py`
- 新增 `vibemouse/bindings/resolver.py`
- 新增 `vibemouse/bindings/actions.py`
- 新增 `vibemouse/ipc/server.py`
- 新增 `vibemouse/ipc/client.py`
- 新增 `vibemouse/ipc/messages.py`
- `vibemouse/doctor.py` -> 拆入 `vibemouse/ops/`
- `vibemouse/deploy.py` -> 拆入 `vibemouse/ops/`

测试映射：

- `tests/test_main.py` -> `tests/cli/test_main.py`
- `tests/test_app.py`、`test_audio.py`、`test_output.py` -> `tests/core/`
- `tests/test_config.py` -> `tests/config/`
- `tests/test_system_integration.py` -> `tests/platform/`
- `tests/test_mouse_listener.py`、`tests/test_keyboard_listener.py` -> `tests/listener/`
- 新增 binding 测试 -> `tests/bindings/`
- 新增 IPC 测试 -> `tests/ipc/`
- `tests/test_doctor.py`、`tests/test_deploy.py` -> `tests/ops/`

### 第 1 步执行顺序

推荐顺序如下：

1. 创建 `panel/` 和 `shared/`
2. 引入 `config.json`、`status.json`、schema、store、migration
3. 定义语义命令，并完成“具象操作名 -> 语义命令”的改名
4. 拆出 `listener`、`bindings`、`core`
5. 加入 agent IPC，并落地 `listener=child` / `listener=off`
6. 引入新命令和新模块路径后，在同一 PR 内完成旧入口的迁移，不跨 PR 保留兼容路径
7. 把 Windows 适配并回主线
8. 补齐 macOS 适配
9. 重组测试，并补 binding / IPC 覆盖
10. 把 CI 改成 Linux / Windows / macOS
11. 继续从当前仓库根目录发布

直接回答“前面聊的这些内容在第几步执行”：

- 操作改名：**第 1 步，第 3 项**
- listener / agent 拆分：**第 1 步，第 4 项**
- IPC 边界和 `listener=off`：**第 1 步，第 5 项**

### 第 1 步交付物

- `vibemouse` 仍然从仓库根目录构建
- agent 接收的是语义命令，不再是具象按键概念
- listener 可以作为子进程运行，也可以关闭
- IPC 成为稳定边界
- 主线代码已具备 Windows + macOS + Linux 支持
- panel 能安全管理配置并读取状态
- doctor / deploy 已按平台分发
- 三平台测试通过

### 第 1 步兼容性要求

- 包名继续保持 `vibemouse`
- 尽量保留现有 CLI 入口
- 环境变量继续保留为覆盖项
- 侧键背后的产品语义保持不变
- 内部改名在引入变更的同一 PR 内完成，不保留跨 PR 的兼容适配

### 第 1 步风险

- 包内 import 路径调整
- 平台并回时误伤 Linux
- 事件和命令契约在重构中漂移
- IPC 在协议还没收窄前过度扩张
- panel 提前膨胀

### 第 1 步风险控制

- 先定义 command，再改 listener
- 先定义 IPC schema，再接多个 IPC 客户端
- 能先搬文件就先搬文件，再改更深的行为
- listener / binding / IPC 测试先补，再大规模并平台
- panel 先保持窄边界

## 第 2 步：升级为最终 monorepo 结构

### 第 2 步目标

在第 1 步边界稳定后，只做仓库组织层面的 monorepo 包装，不再重新设计运行时。

### 第 2 步后的结构

```text
VibeMouse/
  agent/
    pyproject.toml
    vibemouse/
      cli/
      core/
      config/
      platform/
      listener/
      bindings/
      ipc/
      ops/
    tests/
      cli/
      core/
      config/
      platform/
      listener/
      bindings/
      ipc/
      ops/
  panel/
  shared/
  docs/
  scripts/
```

### 第 2 步范围

#### A. 把 Python 项目整体挪到 `agent/`

这一步本质上主要是目录调整：

- `pyproject.toml` 挪到 `agent/`
- `vibemouse/` 挪到 `agent/vibemouse/`
- Python 测试挪到 `agent/tests/`

import 包名仍然必须保持 `vibemouse`。

#### B. 让 `panel/` 成为独立子项目

到第 2 步时，`panel/` 应该成为真正的 UI 子项目，具备：

- 自己的构建配置
- 薄平台 host bridge
- UI 和配置/状态服务层

#### C. 让 `shared/` 成为契约层

`shared/` 保存：

- config / status / IPC schema
- 示例配置
- 协议文档
- 打包和发布文档

#### D. 保持统一发布策略

发布建议：

- 一个版本 tag，例如 `v0.4.0`
- agent 按平台产出资产
- panel 按平台产出资产
- changelog 仍然按产品版本统一

### 第 2 步执行顺序

1. 把 Python 包和测试挪进 `agent/`
2. 把 Python 打包元数据挪进 `agent/`
3. 更新 CI 和 release 脚本路径
4. `panel/` 和 `shared/` 保持原地不动
5. 从 monorepo 根目录验证构建和发布

### 第 2 步交付物

- agent 成为 monorepo 子项目
- panel 成为并列子项目
- shared 中的 schema 和协议稳定
- CI / 发布可以从 monorepo 根目录驱动

### 第 2 步迁移成本

如果第 1 步做对了，第 2 步主要只是：

- 搬目录
- 改 CI 路径
- 改 release 脚本
- 改文档路径

理论上不应该再发生一次运行时大重构。

## 为什么这条路线的迁移成本最低

关键在这几个决策：

### 1. 不改 Python 包名

整个迁移过程中都保持 `vibemouse`，避免第二轮 import、脚本、打包改动。

### 2. 第 1 步就引入 `panel/` 和 `shared/`

这样第 2 步只是“搬进去”，不是“重新定义边界”。

### 3. 第 1 步就完成命令改名、listener 拆分、IPC 引入

这些是运行时契约，必须先稳定，再做 monorepo 包装。

### 4. 第 1 步就切到 JSON 主配置

否则 panel 上来以后还要再做一次结构级改造。

### 5. 先有边界，再并平台

Windows 和 macOS 应该建立在 `listener / bindings / ipc / core` 这些清晰边界上，而不是先并平台、后补边界。

## 配置模型

### 主文件

- `config.json`：用户配置
- `status.json`：运行状态

### 配置解析顺序

1. 加载默认值
2. 加载 `config.json`
3. 如有需要做版本迁移
4. 校验并归一化
5. 应用环境变量覆盖

### 所有权

- panel 写 `config.json`
- agent 读 `config.json`
- agent 写 `status.json`
- panel 读 `status.json`

### 建议配置段

- `bindings`
- `transcriber`
- `output`
- `runtime`
- `platform`
- `startup`
- `logs`

## Agent、Listener、Panel 的契约

### Agent

负责：

- IPC server
- binding resolver
- core 状态机
- 录音 / 转写 / 输出
- 平台集成
- 状态写入

### Listener

负责：

- 原始输入 hook
- 输入归一化
- 在确实贴近设备层时做低层手势抽取

### Panel

负责：

- 配置编辑
- 状态展示
- 有限管理动作

### 共享契约文件和文档

- `config.schema.json`
- `status.schema.json`
- `ipc.schema.json`
- `COMMANDS.md`
- `EVENTS.md`

## 平台支持模型

### Agent 的平台适配

这里仍然需要深平台适配：

- 窗口探测
- 焦点探测
- 快捷键注入
- 光标控制
- 自启动注册
- doctor / deploy

### Panel 的平台适配

这里只需要薄平台适配：

- 配置 / 状态 / 日志路径
- 打开目录和日志
- 启动 / 停止 / 重载 agent
- 自启动 UI 入口
- 打包和签名

## 构建与发布模型

### 版本管理

整个产品采用单一版本线。

例如：

- `v0.4.0`
  - `agent-linux`
  - `agent-windows`
  - `agent-macos`
  - `panel-linux`
  - `panel-windows`
  - `panel-macos`

### 打包

#### Agent

- 一个 Python 包：`vibemouse`
- 依赖通过 marker / extras 按平台分发
- deploy 产出平台特定资产

#### Panel

- 一套 UI 代码
- 一层很薄的 host bridge
- 按平台打包

## 运行时和性能影响

如果严格按这套架构执行，性能影响应当很小。

### 会发生的变化

- 启动时增加 JSON 配置加载和校验
- 启动时增加 backend 选择
- 启动时可能增加 listener 子进程监管
- listener 和 agent 之间新增一层 IPC

### 不应发生的变化

- ASR 仍然是主要开销
- 音频 I/O 仍然是主要开销
- 输入 hook 仍然是主要开销
- 稳态运行时，模块化和 IPC 带来的额外开销应该相对很小

这次迁移的主要价值是架构清晰度、可替换性和跨平台能力，不是性能优化。

## 验收标准

满足以下条件时，可以视为迁移完成：

- 主线架构支持 Windows、macOS、Linux
- core agent 吃的是语义命令，不再吃设备具体按键概念
- listener 可以被监管，也可以被关闭
- `listener=off` 模式可用
- 外部 IPC 客户端可以不依赖内置 listener 直接驱动 agent
- 配置以 JSON 为主，可由 panel 管理
- panel 能安全编辑配置并读取状态
- doctor / deploy 已按平台分发
- CI 在三平台运行
- 单一版本能产出多平台 agent / panel 资产

## 需要避免的反模式

- 长期维护 Linux / Windows / macOS 三套代码分叉
- 为每个平台维护独立版本线
- 在迁移中途改 Python 包名
- 一直拖到 panel 落地后才切 JSON 配置
- 让 listener 拥有业务状态机语义
- 让 panel 直接改 agent 运行时内部对象
- 在 command 和 IPC 都没稳定前就做 monorepo 迁移

## 总结

推荐路线是：

- 第 1 步：在当前仓库根目录内完成 JSON 配置、语义命令、listener 拆分、IPC、panel 边界和三端适配
- 第 2 步：把已经稳定的架构搬到最终 monorepo 结构

这样会把最贵、最容易出回归的工作放在第 1 步处理掉，让第 2 步尽量变成机械搬迁。
