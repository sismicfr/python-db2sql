#!/usr/bin/env bash
# Build a standalone db2sql binary on macOS (arm64 Apple Silicon or x86_64).
#
# Usage:
#   installer/build-macos.sh                   # build with archive
#   installer/build-macos.sh --onedir          # produce a folder bundle
#   PYTHON=python3.12 installer/build-macos.sh # use a specific interpreter
#
# Notes:
#   * PyInstaller does not cross-build between archs. To target arm64, run
#     this script on an Apple Silicon Mac (or under `arch -arm64` shell).
#   * The Oracle driver wheel (oracledb) ships universal binaries; pymssql
#     and psycopg2-binary require arm64 wheels available on PyPI for
#     CPython 3.10+.
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

ARCH="$(uname -m)"
echo "→ building for macOS ${ARCH}"

python installer/build.py --archive "$@"
