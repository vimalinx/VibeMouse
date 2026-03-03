#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$ROOT_DIR/.." && pwd)"
PY_BIN_DEFAULT="$REPO_DIR/.venv/bin/python"

if [[ -x "$PY_BIN_DEFAULT" ]]; then
  PY_BIN="$PY_BIN_DEFAULT"
else
  PY_BIN="python3"
fi

"$PY_BIN" -m pip install -U pip
"$PY_BIN" -m pip install -r "$ROOT_DIR/requirements.txt"

openclaw plugins install -l "$ROOT_DIR"
openclaw plugins enable openclaw-stt
openclaw config set plugins.entries.openclaw-stt.config.pythonBin "$PY_BIN"
openclaw config set plugins.entries.openclaw-stt.config.scriptPath "$ROOT_DIR/stt_cli.py"
openclaw plugins doctor

echo "Installed openclaw-stt plugin with python: $PY_BIN"
