# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

(To be filled by the team)

## Scenario: Software Integration Smoke Command

### 1. Scope / Trigger

- Trigger: adding or changing `vibemouse smoke`, settings API reload behavior, IPC command authentication, config/status normalization, or backend availability payloads.
- The smoke command is an integration-contract check, not a hardware or production-daemon check.

### 2. Signatures

- CLI: `vibemouse smoke [--config <path>]`
- Runner: `run_smoke(args) -> int`
- Check runner: `run_smoke_checks(config_path: Path | None = None) -> list[SmokeCheck]`
- Check record: `SmokeCheck(name: str, status: str, detail: str)`

### 3. Contracts

- Default mode must run in a temporary workspace with temporary config and status files.
- `--config <path>` must require an existing file, load and normalize it, then copy the normalized document to a temporary config before mutable checks.
- Smoke must not write to the real config's `runtime.status_file`.
- Smoke must not control the production daemon; reload checks use a temporary `AgentCommandServer`.
- Settings API checks must use a fake backend status reader to avoid model initialization or hardware access.
- Output must include one line per check with `[OK]`, `[WARN]`, or `[FAIL]`, followed by a summary.
- Exit code must be `0` only when no required check has status `fail`.

### 4. Validation & Error Matrix

- Missing `--config` path -> `config-load` fail and nonzero exit.
- Invalid config JSON -> `config-load` fail and nonzero exit.
- Invalid normalized config shape -> `config-load` fail and nonzero exit.
- Status round-trip mismatch -> `status-shapes` fail and nonzero exit.
- `/api/config` missing normalized profiles -> `settings-config` fail and nonzero exit.
- `/api/status` missing available fake default backend -> `settings-status` fail and nonzero exit.
- `/api/reload` without `ipc_port` returning anything except `daemon_not_running` -> `settings-reload-offline` fail and nonzero exit.
- Authenticated reload not delivering `reload_config` -> `settings-reload-authenticated` fail and nonzero exit.
- Unauthenticated command accepted when a token is configured -> `command-auth` fail and nonzero exit.

### 5. Good/Base/Bad Cases

- Good: `vibemouse smoke --config ~/.config/vibemouse/config.json` validates that config but writes status only under a temporary directory.
- Base: `vibemouse smoke` succeeds on a clean developer machine without an existing user config.
- Bad: `vibemouse smoke --config missing.json` passes by silently falling back to defaults.

### 6. Tests Required

- CLI dispatch test: `smoke` calls the smoke runner and does not instantiate the runtime app.
- Success test: default smoke returns `0` and prints check names plus summary.
- Isolation test: `--config <path>` does not create or modify the real status file or config file.
- Failure test: invalid or missing config returns nonzero and prints the failing `config-load` detail.

### 7. Wrong vs Correct

#### Wrong

Run reload/status checks directly against the user's configured `runtime.status_file` or current daemon port.

#### Correct

Validate the supplied config first, then run mutable checks against a temporary normalized copy with a temporary status file and command server.

## Scenario: Linux Audio Capture and Enhanced ASR Accuracy

### 1. Scope / Trigger

- Trigger: changing `vibemouse.core.audio.AudioRecorder`, transcription backend selection, FunASR enhanced initialization, VAD settings, or anything that can affect captured waveform quality before ASR.
- This is a runtime integration path: a capture can be technically successful and still unusable if it bypasses the user's desktop microphone routing.

### 2. Signatures

- Recorder constructor: `AudioRecorder(sample_rate: int, channels: int, dtype: str, temp_dir: Path)`
- Device resolver: `AudioRecorder._resolve_input_device() -> int | str | None`
- Sample-rate fallback: `AudioRecorder._resolve_device_sample_rate(device: int | str | None) -> int | None`
- Enhanced backend init: `FunASREnhancedBackend(config: AppConfig)`
- Enhanced decode: `transcribe(audio_path: Path, *, hotwords: HotwordList) -> str`

### 3. Contracts

- Linux desktop capture must prefer session-routed input devices named `default`, `pipewire`, or `pulse` before raw ALSA hardware such as `hw:0,0`.
- Monitor devices must never be selected for microphone capture.
- If no session-routed input exists, fallback to a usable physical input device is allowed.
- Enhanced FunASR must enable `vad_model="fsmn-vad"` when `config.enable_vad` is true.
- Enhanced FunASR must pass `vad_kwargs.max_single_segment_time` from `config.vad_max_single_segment_ms`.
- Enhanced decode must pass `merge_vad` from `config.merge_vad` when VAD is enabled.
- Enhanced decode must keep punctuation enabled and normalize CJK token spacing after model output.

### 4. Validation & Error Matrix

- Default device is raw ALSA but `pipewire` exists -> select `pipewire`, not raw ALSA.
- Default device is virtual `default` -> select `default`.
- Only physical microphone exists -> select physical microphone.
- Only monitor inputs exist -> return `None` and let stream startup fail explicitly.
- `enable_vad=true` -> AutoModel kwargs include `vad_model`, `vad_kwargs`, and `merge_length_s`.
- `enable_vad=false` -> AutoModel kwargs omit VAD fields.

### 5. Good/Base/Bad Cases

- Good: systemd service sees raw `hw:0,0` as default but also sees `pipewire`; recorder selects `pipewire`.
- Base: desktop shell exposes `default` as the default input; recorder selects `default`.
- Bad: resolver skips virtual inputs and records from raw HDA hardware, bypassing the user's selected microphone and noise-processing path.

### 6. Tests Required

- Unit test: raw ALSA default plus `pipewire` candidate resolves to `pipewire`.
- Unit test: virtual default resolves to default.
- Unit test: no session input falls back to physical input while monitor inputs are ignored.
- Unit test: enhanced backend initializes AutoModel with VAD kwargs when enabled.
- Unit test: enhanced backend omits VAD kwargs when disabled.
- Unit test: enhanced decode passes `merge_vad` and normalizes CJK spacing without deleting English spaces.

### 7. Wrong vs Correct

#### Wrong

Pick the first non-monitor non-virtual input device after default resolution. On many Linux desktops this selects raw ALSA hardware and bypasses PipeWire/PulseAudio routing.

#### Correct

Prefer `default`, `pipewire`, and `pulse` input devices first; only use raw hardware when no session-routed microphone device is available.

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

(To be filled by the team)

---

## Required Patterns

<!-- Patterns that must always be used -->

(To be filled by the team)

---

## Testing Requirements

<!-- What level of testing is expected -->

(To be filled by the team)

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
