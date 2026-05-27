#!/usr/bin/env bash
# 在项目内启动后端（使用 backend/.venv，不依赖全局 Python 包）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

# Whisper 模型目录（项目内专用，非 .cache）
export HUGGINGFACE_HUB_CACHE="$ROOT/backend/models"
mkdir -p "$HUGGINGFACE_HUB_CACHE"

if [ ! -d ".venv" ]; then
  echo "未找到 .venv，请先执行："
  echo "  cd $ROOT/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Mac Apple Silicon（MLX）走官网；Windows/Linux 默认 hf-mirror 镜像
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  export HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
else
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
fi

exec .venv/bin/uvicorn app:app --reload --host 127.0.0.1 --port 8000
