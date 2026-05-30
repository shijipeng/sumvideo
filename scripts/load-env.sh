#!/usr/bin/env bash
# 根据 SUMVIDEO_ENV（dev | desktop）导出端口/URL，与 config/environments.json 一致
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_NAME="${SUMVIDEO_ENV:-dev}"

eval "$(
  node -e "
const c = require('${ROOT}/config/environments.json');
const p = c['${ENV_NAME}'];
if (!p) { console.error('未知 SUMVIDEO_ENV=${ENV_NAME}'); process.exit(1); }
const b = p.backend;
const f = p.frontend || {};
console.log('export SUMVIDEO_ENV=${ENV_NAME}');
console.log('export SUMVIDEO_BACKEND_HOST=' + b.host);
console.log('export SUMVIDEO_BACKEND_PORT=' + b.port);
console.log('export SUMVIDEO_BACKEND_URL=' + b.url);
if (f.port) {
  console.log('export SUMVIDEO_FRONTEND_PORT=' + f.port);
  console.log('export SUMVIDEO_FRONTEND_URL=' + f.url);
}
"
)"
