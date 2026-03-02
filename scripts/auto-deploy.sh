#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

PYTHON_BIN="${VIBEMOUSE_PYTHON_BIN:-python3}"

if [[ -n "${VIBEMOUSE_PYTHON_BIN:-}" ]]; then
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "指定解释器不可用：${PYTHON_BIN}"
    exit 1
  fi
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3，请先安装 Python 3.10-3.12。"
    exit 1
  fi

  PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  if [[ "${PY_VER}" == "3.13" || "${PY_VER}" == 3.1[4-9] || "${PY_VER}" == [4-9].* ]]; then
    if command -v python3.12 >/dev/null 2>&1; then
      echo "检测到系统默认 Python ${PY_VER}，自动切换到 python3.12（当前依赖链对 3.13+ 不稳定）。"
      PYTHON_BIN="python3.12"
    else
      echo "检测到系统默认 Python ${PY_VER}，但未找到 python3.12。"
      echo "请先安装 Python 3.12（例如 macOS 使用 Homebrew：brew install python@3.12）。"
      exit 1
    fi
  fi
fi

TARGET_VER="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"

if [[ -x ".venv/bin/python" ]]; then
  CURRENT_VENV_VER="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
  if [[ -n "${CURRENT_VENV_VER}" && "${CURRENT_VENV_VER}" != "${TARGET_VER}" ]]; then
    BACKUP_DIR=".venv.backup.${CURRENT_VENV_VER//./_}.$(date +%Y%m%d_%H%M%S)"
    echo "检测到现有 .venv 为 Python ${CURRENT_VENV_VER}，与目标 ${TARGET_VER} 不一致，已备份到 ${BACKUP_DIR}。"
    mv .venv "${BACKUP_DIR}"
  fi
fi

if [[ ! -d ".venv" ]]; then
  "${PYTHON_BIN}" -m venv .venv
fi

source "${REPO_ROOT}/.venv/bin/activate"

pip install -U pip setuptools wheel
pip install -e .

vibemouse deploy "$@"
