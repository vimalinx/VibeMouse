# VibeMouse Two-Step Migration Plan

## Goal

This document defines the migration route from the current Linux-first single-package
project to the target version:

- full Windows + macOS + Linux support
- `agent` and `panel` split
- `panel` acts as the config UI and manages JSON configuration
- `agent` core becomes platform-agnostic
- `listener` becomes independently replaceable
- IPC becomes a first-class integration boundary
- one product version, with platform-specific release assets

The migration is intentionally split into two steps:

- Step 1 changes runtime boundaries and behavior contracts
- Step 2 changes repository packaging into the final monorepo layout

## Short Answer: Which Step Does What

The changes discussed most recently all belong to **Step 1**, not Step 2.

- rename concrete input operations to semantic agent commands: **Step 1**
- split `listener` from `agent`: **Step 1**
- introduce normalized input events and binding resolution: **Step 1**
- introduce the agent IPC boundary and runtime modes (`listener=child` / `listener=off`): **Step 1**
- merge Windows support and add macOS support on top of those boundaries: **Step 1**
- move the already-stable Python project under `agent/`: **Step 2**

Step 2 should not redefine runtime semantics again. It should be mostly a directory move.

## Terminology

- `agent`: the long-running runtime that owns IPC, binding resolution, state machine,
  recording, transcription, output routing, platform integration, doctor, and deploy
- `listener`: the raw input capture component that watches mouse/keyboard activity and
  emits normalized input events
- `panel`: the config and status UI; it edits `config.json`, reads `status.json`, and
  triggers limited control actions
- `normalized input event`: a device-neutral event such as `mouse.side_front.press`
- `agent command`: a semantic command such as `toggle_recording`
- `config.json`: the main persisted configuration file, owned by the panel
- `status.json`: the runtime status file, owned by the agent

## Current Repository State

Current structure:

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

Current characteristics:

- runtime is effectively Linux + Hyprland focused
- config is environment-variable driven
- platform logic is mixed into runtime modules
- listener concerns and core behavior are coupled
- input is still described too concretely in parts of the code and docs
- `doctor` and `deploy` are Linux-biased
- no stable IPC boundary exists
- no stable `agent` / `listener` / `panel` contract exists

## Target Architecture

### Final shape after Step 2

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

### Core flow

The target runtime flow is:

```text
raw input
-> listener
-> normalized input event
-> agent IPC
-> binding resolver
-> semantic agent command
-> core state machine
```

External integrations can bypass the listener and send commands directly:

```text
external client
-> agent IPC
-> semantic agent command
-> core state machine
```

That enables two supported runtime modes:

- default mode: agent starts and supervises a listener child process
- `listener=off` mode: agent starts without a listener child and only accepts external command input

## Core Design Decisions

### 1. Core agent must not depend on physical device semantics

The core agent should not consume inputs such as:

- `front_button_pressed`
- `rear_button_pressed`
- `BTN_SIDE`
- `mouse:275`

The core agent should consume semantic commands such as:

- `toggle_recording`
- `trigger_secondary_action`
- `workspace_left`
- `workspace_right`
- `reload_config`
- `shutdown`

### 2. Product semantics stay in shared core

These behaviors remain shared across all platforms:

- `toggle_recording` toggles the recording state machine
- `trigger_secondary_action` sends Enter while idle
- `trigger_secondary_action` stops recording and routes transcript when recording
- text output fallback must never silently drop text

This logic remains in shared core, not in listener backends.

### 3. Listener emits normalized events, not business commands

The listener is responsible for:

- global mouse hooks
- global keyboard hooks
- optional gesture detection close to raw input when necessary
- emitting normalized events

The listener is not responsible for:

- reading full business config
- owning the state machine
- deciding final agent behavior

### 4. Binding resolution lives in the agent

Binding resolution should remain in the agent because:

- the panel owns `config.json`
- config migration and reload stay centralized
- external IPC clients can bypass listener event mapping
- listener children stay simpler and more replaceable

### 5. IPC is the stable integration boundary

IPC should support at least:

- normalized input events from listener to agent
- semantic commands from external clients to agent
- administrative commands from panel to agent
- status and health responses from agent

### 6. Standardize the built-in IPC transport as `stdio + LPJSON`

For the built-in `agent <-> listener` path, the transport should be fixed to:

- `stdio`
- LPJSON, meaning length-prefixed JSON messages

Recommended framing:

- 4-byte little-endian unsigned length prefix
- UTF-8 JSON payload
- one logical message per frame

Reasons:

- works consistently on Windows, macOS, and Linux
- natural fit for a supervised child process
- avoids port allocation and firewall issues
- easy to implement in Python, Node, Rust, and Go

This choice applies to the built-in listener subprocess path.

For Step 1, panel control does not need a persistent IPC server. It can continue to use:

- `config.json`
- `status.json`
- local command invocation for actions such as reload, restart, and doctor

If a later external control transport is added, it should reuse the same command schema
even if the transport is different.

## Command Renaming and Event Model

### Rename rule

Physical inputs become normalized events first. Normalized events are then mapped to
semantic commands.

### Examples

| Old concrete wording | Normalized event | Semantic command |
| --- | --- | --- |
| front side button | `mouse.side_front.press` | `toggle_recording` |
| rear side button | `mouse.side_rear.press` | `trigger_secondary_action` |
| hotkey combo | `hotkey.record_toggle` | `toggle_recording` |
| gesture left | `gesture.left` | `workspace_left` |
| gesture right | `gesture.right` | `workspace_right` |

### Example config shape

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

## Why Two Steps

Doing everything at once would combine:

- cross-platform adaptation
- config-system replacement
- input model redesign
- listener/agent split
- IPC introduction
- panel introduction
- package refactor
- monorepo packaging
- CI and release restructuring

That is too much change in one pass.

The purpose of the two-step route is:

- Step 1: establish runtime boundaries and contracts in the current repository
- Step 2: package those already-stable boundaries into the final monorepo

## Step 1: Transitional Integration in the Current Repository

### Step 1 objective

Finish the runtime architecture shift while staying in the current root package layout.
This is where the real behavior and boundary work happens.

### Step 1 resulting structure

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

### Step 1 scope

#### A. Introduce JSON config and status ownership

Split config responsibilities into:

- `schema.py`: validated config model and defaults
- `store.py`: JSON load/save/atomic write
- `env_overrides.py`: optional environment overrides
- `migration.py`: config file version migration logic

Introduce:

- `shared/schema/config.schema.json`
- `shared/schema/status.schema.json`
- `shared/examples/config.example.json`

Ownership rules:

- panel writes `config.json`
- agent reads `config.json`
- agent writes `status.json`
- panel reads `status.json`

#### B. Introduce semantic agent commands

This is the point where input-facing names are renamed from concrete device wording to
semantic commands.

Add core command definitions, for example:

- `toggle_recording`
- `trigger_secondary_action`
- `workspace_left`
- `workspace_right`
- `reload_config`
- `shutdown`

This is a **Step 1 change**, not a Step 2 change.

#### C. Split listener from core agent

Replace the old tightly-coupled input path with these layers:

- `listener/`: raw capture and normalization
- `bindings/`: event-to-command mapping
- `core/`: state machine and business behavior

This is also a **Step 1 change**.

#### D. Introduce the IPC runtime boundary

Add:

- `ipc/server.py`
- `ipc/client.py`
- `ipc/messages.py`
- `shared/schema/ipc.schema.json`
- `shared/protocol/COMMANDS.md`
- `shared/protocol/EVENTS.md`

Required capabilities:

- listener sends normalized events to agent over IPC
- panel can trigger limited administrative actions without mutating runtime internals
- external clients can send semantic commands directly when the agent is run in an attached control mode
- agent can run with listener supervision enabled or disabled

Transport decision for the built-in path:

- `agent <-> listener(child)` uses `stdio + LPJSON`

This is the point where `listener=off` mode is introduced and standardized.

#### E. Add runtime modes

Recommended modes:

- `vibemouse agent run --listener=child`
- `vibemouse agent run --listener=off`
- `vibemouse listener run --connect ...`

The new commands (`vibemouse agent run`, `vibemouse listener run`) are introduced in the same PR. The existing CLI entry points (`vibemouse run`, `vibemouse doctor`, `vibemouse deploy`) should be preserved where practical. Removing them is only acceptable if the cost of keeping them is too high; any removal must happen in the same PR that introduces the replacement, never left dangling across PRs.

#### F. Merge platform support behind the new boundaries

Once `core`, `listener`, `bindings`, and `ipc` are in place:

- merge Windows support from the standalone Windows adaptation
- add macOS support using the same boundary model
- keep Linux as the regression baseline

This ordering matters. Platform work should land after the command and listener split,
so it is built on the correct architecture.

#### G. Create the panel boundary

Create `panel/` in Step 1, but keep its scope narrow:

- edit `config.json`
- read `status.json`
- open config/log directories
- send limited control commands such as reload, restart, doctor

Do not let panel take over:

- raw input capture
- device hooks
- audio capture
- state-machine behavior

#### H. Reorganize tests and CI

Split tests by responsibility:

- `tests/cli/`
- `tests/core/`
- `tests/config/`
- `tests/platform/`
- `tests/listener/`
- `tests/bindings/`
- `tests/ipc/`
- `tests/ops/`

Add a CI matrix for:

- Linux
- Windows
- macOS

### Step 1 file mapping

Current files to transitional structure:

- `vibemouse/main.py` -> `vibemouse/cli/main.py`
- `vibemouse/app.py` -> `vibemouse/core/app.py`
- `vibemouse/audio.py` -> `vibemouse/core/audio.py`
- `vibemouse/output.py` -> `vibemouse/core/output.py`
- `vibemouse/transcriber.py` -> `vibemouse/core/transcriber.py`
- `vibemouse/logging_setup.py` -> `vibemouse/core/logging_setup.py`
- `vibemouse/config.py` -> split into `vibemouse/config/`
- `vibemouse/system_integration.py` -> split into `vibemouse/platform/`
- `vibemouse/mouse_listener.py` -> split into `vibemouse/listener/`
- `vibemouse/keyboard_listener.py` -> split into `vibemouse/listener/`
- new `vibemouse/core/commands.py`
- new `vibemouse/bindings/resolver.py`
- new `vibemouse/bindings/actions.py`
- new `vibemouse/ipc/server.py`
- new `vibemouse/ipc/client.py`
- new `vibemouse/ipc/messages.py`
- `vibemouse/doctor.py` -> split into `vibemouse/ops/`
- `vibemouse/deploy.py` -> split into `vibemouse/ops/`

Test mapping:

- `tests/test_main.py` -> `tests/cli/test_main.py`
- `tests/test_app.py`, `test_audio.py`, `test_output.py` -> `tests/core/`
- `tests/test_config.py` -> `tests/config/`
- `tests/test_system_integration.py` -> `tests/platform/`
- `tests/test_mouse_listener.py`, `test_keyboard_listener.py` -> `tests/listener/`
- new binding tests -> `tests/bindings/`
- new IPC tests -> `tests/ipc/`
- `tests/test_doctor.py`, `tests/test_deploy.py` -> `tests/ops/`

### Step 1 execution order

This is the recommended order inside Step 1:

1. create `panel/` and `shared/`
2. introduce `config.json`, `status.json`, schema, store, and migration
3. define semantic agent commands and rename concrete operations
4. split `listener`, `bindings`, and `core` responsibilities
5. add agent IPC and the `listener=child` / `listener=off` runtime modes
6. after introducing new commands and module paths, complete migration of old entry points in the same PR; do not keep compatibility paths across PRs
7. merge Windows support into the mainline
8. add macOS support on the same boundaries
9. reorganize tests by responsibility and add IPC/binding coverage
10. switch CI to Linux/Windows/macOS
11. continue releasing from the repository root

The direct answer to "when do we do the operation renaming and listener split?" is:

- operation renaming: **Step 1, item 3**
- listener/agent split: **Step 1, item 4**
- IPC boundary and `listener=off`: **Step 1, item 5**

### Step 1 deliverables

- shared `vibemouse` package still builds from the repository root
- the agent accepts semantic commands instead of physical-button concepts
- the listener can run as a supervised child or be disabled
- IPC exists as a stable boundary
- Windows + macOS + Linux are supported in the main package
- panel can safely manage config and read status
- doctor and deploy are platform-aware
- tests pass on all three platforms

### Step 1 compatibility rules

- keep package name `vibemouse`
- preserve current CLI behavior where practical
- preserve environment variables as optional overrides
- preserve the product semantics behind side-button behavior
- complete internal command renames within the same PR that introduces them; no cross-PR compatibility adapters

### Step 1 risks

- import-path churn
- Linux regressions during platform merge
- event/command contract drift during refactor
- overcomplicating IPC before the protocol is narrowed
- expanding panel scope too early

### Step 1 risk controls

- define commands before rewriting listeners
- define IPC schema before introducing multiple IPC clients
- move files before changing deeper behavior where possible
- add listener, binding, and IPC tests before broad platform rollout
- keep panel scope narrow until contracts are stable

## Step 2: Final Monorepo Packaging

### Step 2 objective

Convert the already-stable Step 1 architecture into the final monorepo shape without
changing runtime semantics again.

### Step 2 resulting structure

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

### Step 2 scope

#### A. Move the Python project under `agent/`

This is mostly a repository-layout move:

- move `pyproject.toml` into `agent/`
- move `vibemouse/` into `agent/vibemouse/`
- move Python tests into `agent/tests/`

The import package name must still remain `vibemouse`.

#### B. Keep `panel/` as a sibling project

By Step 2, `panel/` becomes a full product directory with:

- its own build/package config
- thin platform host adapters
- UI and config/status services

#### C. Keep `shared/` as the contract layer

Shared assets should include:

- config, status, and IPC schemas
- example config files
- protocol docs
- packaging and release docs

#### D. Keep release versioning unified

Release policy:

- one version tag, for example `v0.4.0`
- agent assets per platform
- panel assets per platform
- one changelog per product version

### Step 2 execution order

1. move Python package and tests under `agent/`
2. move Python packaging metadata under `agent/`
3. update CI and release scripts for the monorepo layout
4. keep `panel/` and `shared/` in place
5. verify packaging and release assets from the monorepo root

### Step 2 deliverables

- agent is a monorepo subproject
- panel is a sibling subproject
- shared schemas and protocols are stable
- CI and release automation work from the monorepo root

### Step 2 migration cost

If Step 1 was done correctly, Step 2 is mostly:

- moving directories
- updating CI paths
- updating release scripts
- updating docs

It should not require another runtime redesign.

## Why This Route Minimizes Migration Cost

The key cost-saving decisions are:

### Keep the package name stable

Do not rename `vibemouse` during migration.

### Introduce `panel/` and `shared/` in Step 1

That prevents a second conceptual split later.

### Introduce commands, listener split, and IPC in Step 1

Those are runtime contracts. They should stabilize before monorepo packaging.

### Make JSON config primary in Step 1

Otherwise the panel integration will need a second structural rewrite later.

### Merge platforms after boundaries exist

Windows and macOS should be built on top of the listener/bindings/ipc split, not before it.

## Config Model

### Primary files

- `config.json`: user-owned runtime configuration
- `status.json`: agent-owned runtime status

### Resolution order

1. load defaults
2. load `config.json`
3. migrate old config versions if needed
4. validate and normalize
5. apply optional environment overrides

### Ownership

- panel writes `config.json`
- agent reads `config.json`
- agent writes `status.json`
- panel reads `status.json`

### Suggested config sections

- `bindings`
- `transcriber`
- `output`
- `runtime`
- `platform`
- `startup`
- `logs`

## Agent, Listener, and Panel Contract

### Agent

Owns:

- IPC server
- binding resolution
- core state machine
- recording/transcription/output
- platform integration
- status writing

### Listener

Owns:

- raw input hooks
- input normalization
- optional low-level gesture extraction when truly device-close

### Panel

Owns:

- config editing
- status display
- limited administrative actions

### Shared contract files and docs

- `config.schema.json`
- `status.schema.json`
- `ipc.schema.json`
- `COMMANDS.md`
- `EVENTS.md`

## Platform Support Model

### Agent platform adaptation

Deep platform-specific behavior remains here:

- window detection
- focus detection
- shortcut injection
- cursor control
- startup registration
- doctor and deploy

### Panel platform adaptation

Thin platform-specific behavior only:

- config/status/log paths
- open directories and logs
- start/stop/reload agent
- startup registration UI hooks
- packaging and signing

## Build and Release Model

### Versioning

Use one shared version line across the product.

Example:

- `v0.4.0`
  - `agent-linux`
  - `agent-windows`
  - `agent-macos`
  - `panel-linux`
  - `panel-windows`
  - `panel-macos`

### Packaging

#### Agent

- one Python package named `vibemouse`
- platform dependencies via markers and extras
- platform-specific deploy assets

#### Panel

- one UI codebase
- thin host layer
- platform-specific distributables

## Runtime and Performance Impact

Expected runtime impact is small if this architecture is followed.

### Expected changes

- startup adds JSON config load and validation
- startup adds backend selection
- startup may add listener child process supervision
- IPC adds one more boundary between listener and agent

### Expected non-changes

- ASR cost remains dominant
- audio I/O remains dominant
- input hook cost remains dominant
- steady-state overhead from modularization and IPC should be small relative to the rest

This migration is primarily about architecture, replaceability, and cross-platform
support, not performance optimization.

## Acceptance Criteria

The migration is complete when all of the following are true:

- mainline architecture supports Windows, macOS, and Linux
- core agent consumes semantic commands instead of device-specific button concepts
- listener can be supervised or disabled
- `listener=off` mode works
- external IPC clients can drive the agent without using the built-in listener
- config is JSON-primary and panel-manageable
- panel can safely edit config and read runtime status
- doctor and deploy are platform-aware
- CI runs on all three platforms
- one version produces platform-specific agent and panel assets

## Anti-Patterns to Avoid

- long-lived Linux / Windows / macOS forks
- separate version lines per platform
- renaming the Python package during migration
- delaying JSON config until after the panel exists
- letting listener own business-state semantics
- letting panel mutate runtime internals directly
- doing the monorepo move before commands and IPC are stable

## Summary

The recommended route is:

- Step 1: introduce JSON config, semantic commands, listener split, IPC, panel
  boundary, and three-platform runtime support inside the current repository root
- Step 2: move that already-stable architecture into the final monorepo layout

This keeps the expensive work in Step 1 and makes Step 2 mostly mechanical.
