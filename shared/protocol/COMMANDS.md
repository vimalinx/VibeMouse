# VibeMouse Agent Commands

Semantic commands that can be sent to the agent via IPC or resolved from input events via bindings.

| Command | Description |
|---------|-------------|
| `noop` | No operation; event is ignored |
| `toggle_recording` | Start or stop voice recording |
| `trigger_secondary_action` | In idle: send Enter. In recording: stop and output the transcript through the default text route |
| `submit_recording` | Stop recording and output the transcript through the default text route |
| `send_enter` | Send Enter key to focused input |
| `workspace_left` | Switch workspace left (e.g. Hyprland) |
| `workspace_right` | Switch workspace right |
| `reload_config` | Reload config.json |
| `shutdown` | Gracefully shut down the agent |

Loopback command messages may include an optional `token` string when the command server is configured with `runtime.command_auth_token`.
