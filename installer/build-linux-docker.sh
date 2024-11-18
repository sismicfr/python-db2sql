#!/usr/bin/env bash
# Build a Debian-12-compatible db2sql binary using docker.
#
# Runs the same build pipeline that release-binaries.yml uses for the linux
# job, inside the python:3.12-bookworm image (Debian 12). The produced
# binary links against glibc 2.36, so it remains runnable on Debian 12,
# Ubuntu 22.10+, RHEL/Rocky 9, and any newer GNU/Linux distribution.
#
# Usage:
#   installer/build-linux-docker.sh                # x86_64, single-file binary + archive
#   installer/build-linux-docker.sh --onedir       # folder bundle instead
#   IMAGE=python:3.11-bookworm installer/build-linux-docker.sh
#   PLATFORM=linux/arm64 installer/build-linux-docker.sh   # cross-build via binfmt
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
IMAGE="${IMAGE:-python:3.12-bookworm}"
PLATFORM="${PLATFORM:-}"
DOCKER="${DOCKER:-docker}"

if ! command -v "$DOCKER" >/dev/null 2>&1; then
    echo "error: '$DOCKER' is not available on PATH" >&2
    exit 1
fi

declare -a platform_args=()
if [[ -n "$PLATFORM" ]]; then
    platform_args=(--platform "$PLATFORM")
fi

# Map host UID/GID into the container so produced files are not owned by root.
USER_ID="$(id -u)"
GROUP_ID="$(id -g)"

echo "→ building inside ${IMAGE}${PLATFORM:+ (${PLATFORM})}"

"$DOCKER" run --rm \
    "${platform_args[@]}" \
    --user "${USER_ID}:${GROUP_ID}" \
    -e HOME=/tmp \
    -e VENV_DIR=/tmp/db2sql-build-venv \
    -e PIP_CACHE_DIR=/tmp/pip-cache \
    -v "$ROOT:/work" \
    -w /work \
    "$IMAGE" \
    bash installer/build-linux.sh "$@"

echo
echo "→ output:"
ls -la "$ROOT/installer/dist"
