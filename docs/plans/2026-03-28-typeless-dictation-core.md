# Typeless Dictation Core Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Linux-first open-source Typeless-style dictation core with `Fast` and `Enhanced` modes, a shared personal dictionary, deterministic normalization, and a local settings UI.

**Architecture:** Extend the JSON config schema with profiles, dictionary entries, and backend settings; replace the single transcriber path with a routed backend layer; and add a lightweight local settings server that edits the same config file the runtime uses. Keep the existing app/output orchestration intact while making backend failures explicit instead of silently downgrading.

**Tech Stack:** Python 3.10+, existing VibeMouse config/store system, current SenseVoice `funasr_onnx` path for `Fast`, a hotword-capable FunASR backend for `Enhanced`, stdlib HTTP server + static HTML/JS for settings UI, pytest for verification.

---

### Task 1: Extend Config Schema For Profiles And Dictionary

**Files:**
- Modify: `vibemouse/config/schema.py`
- Modify: `vibemouse/config/__init__.py`
- Modify: `shared/examples/config.example.json`
- Test: `tests/test_config.py`
- Test: `tests/test_config_store.py`

**Step 1: Write the failing tests**

Add tests for:

```python
def test_default_config_contains_profiles_and_dictionary():
    doc = build_default_config_document()
    assert doc["profiles"] == {"default": "fast"}
    assert doc["dictionary"] == []


def test_config_document_to_app_config_reads_profiles_and_dictionary():
    doc = build_default_config_document()
    doc["profiles"]["default"] = "enhanced"
    doc["dictionary"] = [
        {
            "term": "Codex",
            "phrases": ["codex", "code x"],
            "weight": 8,
            "scope": "both",
            "enabled": True,
        }
    ]
    config = config_document_to_app_config(doc)
    assert config.profiles["default"] == "enhanced"
    assert config.dictionary[0].term == "Codex"
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest -q tests/test_config.py tests/test_config_store.py`

Expected: FAIL because `profiles` / `dictionary` fields do not exist yet.

**Step 3: Write minimal implementation**

Add:

- `profiles` and `dictionary` sections to the config document
- dataclasses for dictionary entries if needed
- normalization and validation for:
  - valid profile names
  - non-empty `term`
  - non-empty `phrases`
  - bounded `weight`
  - valid `scope`

Example target structure:

```python
@dataclass(frozen=True)
class DictionaryEntry:
    term: str
    phrases: tuple[str, ...]
    weight: int
    scope: str
    enabled: bool
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest -q tests/test_config.py tests/test_config_store.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/config/schema.py vibemouse/config/__init__.py shared/examples/config.example.json tests/test_config.py tests/test_config_store.py
git commit -m "feat: add dictation profiles and dictionary config"
```

### Task 2: Add Dictionary Service And Deterministic Normalization

**Files:**
- Create: `vibemouse/core/dictionary.py`
- Test: `tests/core/test_dictionary.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_scope_filters_dictionary_entries():
    service = DictionaryService(entries)
    hotwords = service.hotwords_for_scope("default")
    assert "Codex" in hotwords


def test_normalize_text_rewrites_phrase_to_term():
    service = DictionaryService(entries)
    assert service.normalize("please ask code x to review", scope="both") == "please ask Codex to review"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/core/test_dictionary.py`

Expected: FAIL because the dictionary service does not exist.

**Step 3: Write minimal implementation**

Implement:

- scope filtering
- enabled filtering
- phrase aggregation for `Enhanced`
- deterministic normalization to `term`

Suggested API:

```python
class DictionaryService:
    def hotword_phrases(self, scope: str) -> list[tuple[str, int]]: ...
    def normalize(self, text: str, scope: str) -> str: ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/core/test_dictionary.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/core/dictionary.py tests/core/test_dictionary.py
git commit -m "feat: add dictionary normalization service"
```

### Task 3: Split Transcription Into Routed Fast And Enhanced Backends

**Files:**
- Modify: `vibemouse/core/transcriber.py`
- Create: `vibemouse/core/backends/__init__.py`
- Create: `vibemouse/core/backends/base.py`
- Create: `vibemouse/core/backends/sensevoice_fast.py`
- Create: `vibemouse/core/backends/funasr_enhanced.py`
- Test: `tests/core/test_transcriber.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_router_uses_fast_backend_for_default_profile(): ...
def test_router_uses_enhanced_backend_for_default_profile_when_configured(): ...
def test_router_reports_unavailable_backend_without_silent_downgrade(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/core/test_transcriber.py`

Expected: FAIL because the router and backend protocol do not exist.

**Step 3: Write minimal implementation**

Create a backend protocol:

```python
class TranscriptionBackend(Protocol):
    backend_id: str
    def transcribe(self, audio_path: Path, *, hotwords: list[tuple[str, int]]) -> str: ...
    def availability(self) -> BackendStatus: ...
```

Refactor current SenseVoice logic into `SenseVoiceFastBackend`.

Implement `FunASREnhancedBackend` with these rules:

- import provider lazily
- check availability explicitly
- accept weighted hotwords
- translate dictionary hotwords into provider-specific call arguments
- raise a dedicated unavailable error when dependencies are missing

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/core/test_transcriber.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/core/transcriber.py vibemouse/core/backends tests/core/test_transcriber.py
git commit -m "feat: add routed fast and enhanced transcription backends"
```

### Task 4: Wire App To Profiles, Dictionary, And Explicit Backend Failures

**Files:**
- Modify: `vibemouse/core/app.py`
- Test: `tests/core/test_app.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_default_target_uses_default_profile_and_normalizes_text(): ...
def test_default_target_uses_hotwords(): ...
def test_enhanced_unavailable_logs_explicit_failure(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/core/test_app.py`

Expected: FAIL because `VoiceMouseApp` still assumes one transcriber path.

**Step 3: Write minimal implementation**

Update the app to:

- ask the router for the backend based on output target
- pass the relevant dictionary scope
- normalize final text before output dispatch
- log backend id and profile
- handle unavailable backend errors explicitly

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/core/test_app.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/core/app.py tests/core/test_app.py
git commit -m "feat: route dictation targets through fast and enhanced profiles"
```

### Task 5: Add Backend Status Reporting

**Files:**
- Modify: `vibemouse/core/transcriber.py`
- Create: `vibemouse/core/backend_status.py`
- Test: `tests/core/test_backend_status.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_backend_status_reports_fast_and_enhanced_availability(): ...
def test_unavailable_backend_reports_reason_string(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/core/test_backend_status.py`

Expected: FAIL because no backend status API exists.

**Step 3: Write minimal implementation**

Expose a small status shape:

```python
@dataclass(frozen=True)
class BackendStatus:
    backend_id: str
    available: bool
    reason: str | None
```

Provide a helper that the settings UI and runtime can both call.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/core/test_backend_status.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/core/backend_status.py vibemouse/core/transcriber.py tests/core/test_backend_status.py
git commit -m "feat: expose dictation backend availability status"
```

### Task 6: Add Local Settings HTTP Service

**Files:**
- Create: `vibemouse/settings/__init__.py`
- Create: `vibemouse/settings/server.py`
- Test: `tests/settings/test_server.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_get_config_returns_profiles_and_dictionary(): ...
def test_post_config_persists_updates(): ...
def test_get_status_returns_backend_status(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/settings/test_server.py`

Expected: FAIL because the settings service does not exist.

**Step 3: Write minimal implementation**

Use stdlib `ThreadingHTTPServer` plus JSON handlers for:

- `GET /api/config`
- `POST /api/config`
- `GET /api/status`

Keep persistence inside the existing config store.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/settings/test_server.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/settings tests/settings/test_server.py
git commit -m "feat: add local settings service for dictation profiles"
```

### Task 7: Add Static Settings UI

**Files:**
- Create: `vibemouse/settings/static/index.html`
- Create: `vibemouse/settings/static/app.js`
- Create: `vibemouse/settings/static/styles.css`
- Modify: `vibemouse/settings/server.py`
- Test: `tests/settings/test_server.py`

**Step 1: Write the failing test**

Add a simple test that ensures the static index is served:

```python
def test_root_serves_settings_page(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/settings/test_server.py::test_root_serves_settings_page`

Expected: FAIL because the UI assets are not served.

**Step 3: Write minimal implementation**

The page must include:

- profile selector for `default`
- dictionary table
- add/edit entry form
- backend status panel

Use plain HTML/JS. No frontend framework in stage one.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/settings/test_server.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/settings/static vibemouse/settings/server.py tests/settings/test_server.py
git commit -m "feat: add local web UI for dictation settings"
```

### Task 8: Wire Settings UI Into CLI

**Files:**
- Modify: `vibemouse/cli/main.py`
- Test: `tests/cli/test_main.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_settings_command_starts_local_settings_server(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/cli/test_main.py`

Expected: FAIL because the `settings` command does not exist.

**Step 3: Write minimal implementation**

Add:

- `vibemouse settings`
- optional `--host`
- optional `--port`
- optional `--open-browser`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/cli/test_main.py`

Expected: PASS

**Step 5: Commit**

```bash
git add vibemouse/cli/main.py tests/cli/test_main.py
git commit -m "feat: add settings command for local dictation UI"
```

### Task 9: Add A Small Evaluation Harness

**Files:**
- Create: `scripts/eval_dictation_profiles.py`
- Create: `shared/examples/dictation_eval.jsonl`
- Create: `tests/scripts/test_eval_dictation_profiles.py`

**Step 1: Write the failing test**

Add tests for:

```python
def test_eval_script_scores_term_hits_and_exact_matches(): ...
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/scripts/test_eval_dictation_profiles.py`

Expected: FAIL because no evaluation harness exists.

**Step 3: Write minimal implementation**

Support:

- loading a JSONL fixture
- running `Fast` vs `Enhanced`
- scoring:
  - exact text match
  - dictionary term hit rate
  - backend availability result

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/scripts/test_eval_dictation_profiles.py`

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/eval_dictation_profiles.py shared/examples/dictation_eval.jsonl tests/scripts/test_eval_dictation_profiles.py
git commit -m "test: add dictation profile evaluation harness"
```

### Task 10: Run Full Verification And Update Docs

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `shared/examples/config.example.json`

**Step 1: Run focused verification**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_config.py tests/test_config_store.py tests/core tests/cli tests/settings
```

Expected: PASS

**Step 2: Run full verification**

Run:

```bash
PYTHONPATH=. pytest -q
```

Expected: PASS

**Step 3: Update docs**

Document:

- `Fast / Enhanced`
- dictionary format
- `vibemouse settings`
- explicit enhanced-backend availability behavior

**Step 4: Commit**

```bash
git add README.md README.zh-CN.md shared/examples/config.example.json
git commit -m "docs: document typeless dictation core stage one"
```

Plan complete and saved to `docs/plans/2026-03-28-typeless-dictation-core.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration

2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
