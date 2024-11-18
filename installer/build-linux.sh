#!/usr/bin/env bash
# Build a standalone db2sql binary on Linux (x86_64 or aarch64).
#
# Usage:
#   installer/build-linux.sh                   # build with archive
#   installer/build-linux.sh --onedir          # produce a folder bundle
#   PYTHON=python3.12 installer/build-linux.sh # use a specific interpreter
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-$HERE/.venv-build}"

cd "$ROOT"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "→ creating build venv: $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip wheel
python -m pip install -e ".[all]"
python -m pip install "pyinstaller>=6"

python installer/build.py --archive "$@"
