#!/usr/bin/env bash
# 在 macOS Apple Silicon 上构建桌面用 Python venv，输出到 sumvideo/dist/venv-darwin-arm64
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/dist/venv-darwin-arm64"
PY="${PYTHON:-python3}"

rm -rf "$OUT"
"$PY" -m venv "$OUT"
# shellcheck source=/dev/null
source "$OUT/bin/activate"
pip install -U pip wheel
pip install -r "${ROOT}/backend/requirements-desktop-darwin.txt"
echo "venv ready: $OUT"
