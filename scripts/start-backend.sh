#!/usr/bin/env bash
# 在项目内启动后端（使用 backend/.venv，不依赖全局 Python 包）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/load-env.sh
source "$ROOT/scripts/load-env.sh"
cd "$ROOT/backend"

mkdir -p "$ROOT/backend/models" "$ROOT/backend/uploads" "$ROOT/backend/audio"

if [ ! -d ".venv" ]; then
  echo "未找到 .venv，请先执行："
  echo "  cd $ROOT/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  export HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
else
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
fi

echo "SumVideo 后端 [${SUMVIDEO_ENV}] → ${SUMVIDEO_BACKEND_URL}"

if [ -n "${SUMVIDEO_RELOAD:-}" ]; then
  echo "热重载已开启（处理视频时改代码会中断任务）"
  exec .venv/bin/uvicorn app:app --reload --host "$SUMVIDEO_BACKEND_HOST" --port "$SUMVIDEO_BACKEND_PORT"
fi
exec .venv/bin/uvicorn app:app --host "$SUMVIDEO_BACKEND_HOST" --port "$SUMVIDEO_BACKEND_PORT"
