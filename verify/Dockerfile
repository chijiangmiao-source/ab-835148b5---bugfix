# verify 一次性服务：内含 Python（后端测试与 API 核对）与 Node（前端测试与构建）。
# 构建上下文须为仓库根目录：docker build -f verify/Dockerfile .
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY api /srv/api
COPY web/package*.json /srv/web/
COPY web/index.html /srv/web/index.html
COPY web/vite.config.js /srv/web/vite.config.js
COPY web/src /srv/web/src
COPY verify /srv/verify

RUN chmod +x /srv/verify/run.sh

ENTRYPOINT ["/srv/verify/run.sh"]
