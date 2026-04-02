# VibeMouse Agent Commands

Semantic commands that can be sent to the agent via IPC or resolved from input events via bindings.

| Command | Description |
|---------|-------------|
| `noop` | No operation; event is ignored |
| `toggle_recording` | Start or stop voice recording |
| `trigger_secondary_action` | In idle: send Enter. In recording: stop and send transcript to OpenClaw |
| `submit_recording` | Stop recording and send transcript to OpenClaw |
| `send_enter` | Send Enter key to focused input |
| `workspace_left` | Switch workspace left (e.g. Hyprland) |
| `workspace_right` | Switch workspace right |
| `reload_config` | Reload config.json |
| `shutdown` | Gracefully shut down the agent |
