# VibeMouse Normalized Input Events

Device-agnostic event names produced by the listener and consumed by the binding resolver.

## Mouse events

| Event | Description |
|-------|-------------|
| `mouse.side_front.press` | Front side button press |
| `mouse.side_rear.press` | Rear side button press |

## Keyboard events

| Event | Description |
|-------|-------------|
| `hotkey.record_toggle` | Recording toggle hotkey (e.g. Ctrl+Alt+Space) |
| `hotkey.recording_submit` | Recording submit hotkey (optional) |

## Gesture events

| Event | Description |
|-------|-------------|
| `gesture.up` | Upward gesture |
| `gesture.down` | Downward gesture |
| `gesture.left` | Leftward gesture |
| `gesture.right` | Rightward gesture |

## Event naming convention

Events use dot-separated segments: `category.subcategory.action`. All lowercase, alphanumeric and underscore only.
