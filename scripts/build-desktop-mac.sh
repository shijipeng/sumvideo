#!/usr/bin/env bash
# macOS 桌面包：构建 dmg/zip，完成后删除未压缩的 .app 目录（仅保留安装产物）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/dist/desktop"

cd "$ROOT"
npm run build:web
npx electron-builder --config electron-builder.yml --mac

# electron-builder 必须先产出 .app 才能打 dmg；安装包生成后删除中间目录
shopt -s nullglob
for dir in "${OUT}"/mac "${OUT}"/mac-*; do
  if [[ -d "$dir" ]]; then
    echo "清理未压缩产物: $dir"
    rm -rf "$dir"
  fi
done
shopt -u nullglob

echo ""
echo "安装包已输出到 ${OUT}/"
ls -lh "${OUT}"/*.dmg "${OUT}"/*.zip 2>/dev/null || ls -lh "${OUT}"
