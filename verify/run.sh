#!/usr/bin/env bash
# verify 一次性服务入口：后端单元测试 → 前端单元测试与构建 → 真实 API/页面核对与冒烟。
set -euo pipefail

echo "== [1/4] 后端单元测试（含 500 组随机图暴力对拍）=="
cd /srv/api
python3 -m venv /opt/venv
# shellcheck disable=SC1091
. /opt/venv/bin/activate
pip install --quiet -r requirements-dev.txt
python -m pytest -q

echo "== [2/4] 前端单元测试 =="
cd /srv/web
npm install --no-audit --no-fund
npm test

echo "== [3/4] 前端生产构建 =="
npm run build
test -f dist/index.html
test -n "$(ls -A dist/assets)"

echo "== [4/4] 真实 API 与页面结果核对 + API/HTTP 冒烟 =="
cd /srv/verify
python verify.py
