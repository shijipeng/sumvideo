#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/load-env.sh
source "$ROOT/scripts/load-env.sh"
cd "$ROOT/web"

if [ ! -d "node_modules" ]; then
  echo "未找到 node_modules，请先执行："
  echo "  cd $ROOT/web && npm install"
  exit 1
fi

echo "SumVideo 前端 [${SUMVIDEO_ENV}] → ${SUMVIDEO_FRONTEND_URL}（API 代理 → ${SUMVIDEO_BACKEND_URL}）"
exec npm run dev
