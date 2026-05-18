# Typeless OSS Dictation Core Design

## Goal

Build a realistic first-stage open-source Typeless-style dictation core on top of the current VibeMouse runtime. The first stage must improve practical dictation quality without hiding failures behind silent downgrade behavior.

## Scope

This stage includes:

- Dual dictation modes: `Fast` and `Enhanced`
- Shared personal dictionary with hotword phrases, weights, scopes, and enable flags
- Explicit backend routing for the default output target
- Post-transcription normalization that unifies final display text
- Local settings UI for profile selection, dictionary management, and backend status
- Explicit backend availability reporting with no hidden downgrade

This stage does not include:

- AI polish / rewrite
- Cloud sync or accounts
- Full Windows/macOS platform support
- Complex app-specific writing templates
- More than two user-facing modes

## Product Model

The user does not choose raw model names. The user chooses modes:

- `Fast`
  - Daily-driver mode
  - Uses the existing lightweight local SenseVoice path
  - Favors latency and stability
  - Reads the shared dictionary only for normalization
- `Enhanced`
  - Accuracy-first mode
  - Uses a backend that explicitly supports hotword biasing
  - Reads the shared dictionary for both hotword biasing and normalization

The default output target gets a configurable mode:

- `default` output target

Example:

- `default -> Fast`

This preserves quick local typing while still allowing users to switch to a more expensive recognition mode when needed.

## Architecture

### Runtime Layers

The runtime becomes:

`recording -> profile routing -> backend transcription -> dictionary normalization -> output`

New architectural responsibilities:

- `config`
  - Stores profiles, dictionary entries, and backend configuration
- `transcription router`
  - Chooses backend based on output target profile
- `backend registry`
  - Knows which backends are installed and available
- `dictionary service`
  - Produces hotword payloads for `Enhanced`
  - Produces normalization rules for both modes
- `settings service`
  - Reads/writes config and reports backend status

### Transcription Backends

The current single `SenseVoiceTranscriber` path in [`vibemouse/core/transcriber.py`](/home/vimalinx/Projects/VibeLifes/VibeMouse/vibemouse/core/transcriber.py) should evolve into a router-based structure:

- `TranscriptionBackend`
  - Common interface for all backends
- `SenseVoiceFastBackend`
  - Wraps current `funasr_onnx` SenseVoice flow
- `FunASREnhancedBackend`
  - Wraps a hotword-capable FunASR backend
- `TranscriptionRouter`
  - Picks backend from the target profile

The public app-facing call should remain simple. `core/app.py` should request transcription for a given output target and receive:

- final text
- backend id
- availability / failure metadata

### Failure Policy

No silent downgrade.

If `Enhanced` is configured but unavailable:

- runtime reports `backend_unavailable`
- settings UI shows why
- app logs the failure clearly
- any fallback must be an explicit user-approved policy, not an invisible automatic switch

This avoids the common trap where the advertised premium path is almost never actually used.

## Configuration Model

The current JSON config schema should be extended with three new top-level sections:

```json
{
  "profiles": {
    "default": "fast"
  },
  "dictionary": [
    {
      "term": "Codex",
      "phrases": ["codex", "code x", "扣带思"],
      "weight": 8,
      "scope": "both",
      "enabled": true
    }
  ],
  "backends": {
    "fast": {
      "provider": "sensevoice"
    },
    "enhanced": {
      "provider": "funasr"
    }
  }
}
```

Design rules:

- `profiles.default` accepts only `fast` or `enhanced`
- dictionary entries are independent records, not free-form alias maps
- `phrases` is the source of bias terms
- `term` is the canonical final text
- `scope` controls whether a term applies to `default` or `both`
- `weight` is only consumed by `Enhanced`

The config system already has schema/store infrastructure in [`vibemouse/config/schema.py`](/home/vimalinx/Projects/VibeLifes/VibeMouse/vibemouse/config/schema.py) and [`vibemouse/config/store.py`](/home/vimalinx/Projects/VibeLifes/VibeMouse/vibemouse/config/store.py). This feature should extend that system rather than introduce environment-only configuration.

## Dictionary Semantics

Each dictionary entry serves two distinct purposes.

### 1. Hotword Bias Input

For `Enhanced`, enabled entries with matching scope are converted into hotword payloads. The backend adapter handles provider-specific formatting such as:

- list of phrases
- weighted phrases
- single hotword string

The settings UI owns the user-friendly record; backend adapters own the translation into provider-specific arguments.

### 2. Final Normalization

After transcription, both modes pass the recognized text through a deterministic normalization layer. If a recognized phrase matches an enabled dictionary phrase for the active scope, the final text is normalized to `term`.

This matters even when hotword biasing exists. Biasing improves recognition probability; normalization guarantees the final canonical spelling.

## Settings UI

The first-stage settings UI should be a local Web UI instead of a native desktop shell.

Reasons:

- cross-platform reuse later
- lower dependency overhead
- fast implementation
- enough for configuration-centric workflows

### UI Sections

1. `Profiles`
   - default target mode

2. `Dictionary`
   - list entries
   - add/edit/delete
   - enable/disable
   - edit `term`, `phrases`, `weight`, `scope`

3. `Status`
   - backend availability
   - dependency errors
   - currently configured providers

### Backend UI Service

Implement a lightweight local HTTP server with JSON endpoints and static assets.

Suggested endpoints:

- `GET /api/config`
- `POST /api/config`
- `GET /api/status`
- `GET /api/dictionary`
- `POST /api/dictionary`

The UI should edit the same JSON config file used by the runtime.

## App Integration

`VoiceMouseApp` in [`vibemouse/core/app.py`](/home/vimalinx/Projects/VibeLifes/VibeMouse/vibemouse/core/app.py) should remain the orchestration center, but it should stop knowing backend details.

Integration changes:

- request transcription by output target
- receive routed backend result
- normalize text before output dispatch
- log backend id, route, and any explicit backend failure

Output dispatch in [`vibemouse/core/output.py`](/home/vimalinx/Projects/VibeLifes/VibeMouse/vibemouse/core/output.py) remains mostly unchanged in this stage. The main change is that it will receive higher-quality, already-normalized text.

## Platform Boundary

This stage remains Linux-first.

The current platform layer in [`vibemouse/platform/system_integration.py`](/home/vimalinx/Projects/VibeLifes/VibeMouse/vibemouse/platform/system_integration.py) is still Hyprland-centric. The new feature must not pretend to solve cross-platform injection yet.

What should be cross-platform-friendly now:

- config format
- local settings UI
- dictionary model
- backend abstraction

What remains Linux-scoped:

- listener integration
- direct text injection behavior

## Verification Strategy

The feature should ship with a small deterministic evaluation harness.

Minimum verification:

- schema tests for new config fields
- dictionary normalization unit tests
- router tests for profile selection
- backend availability tests
- settings API tests
- app integration tests for:
  - `default -> Fast`
  - `Enhanced unavailable`

Additionally, add a small manual benchmark fixture format for personal dictation phrases so profile quality can be compared honestly instead of by feel.

## Acceptance Criteria

The first stage is successful when all of the following are true:

- user can choose `Fast` or `Enhanced` per output target
- user can manage dictionary entries in a local settings UI
- `Enhanced` consumes dictionary phrases as hotword input
- both modes normalize final output to canonical terms
- backend unavailability is explicit, never hidden
- the system remains usable when only `Fast` is available
