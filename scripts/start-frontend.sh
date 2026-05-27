#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web"

if [ ! -d "node_modules" ]; then
  echo "未找到 node_modules，请先执行："
  echo "  cd $ROOT/web && npm install"
  exit 1
fi

exec npm run dev
