#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 Docker。请先安装并启动 Docker Desktop。" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker 引擎没有运行。请先启动 Docker Desktop。" >&2
  exit 1
fi

if [[ ! -f ".env" ]]; then
  cp ".env.example" ".env"
  echo "已从 .env.example 创建本地 .env。"
fi

echo "正在构建并启动砚台本地服务……"
docker compose up -d --build

echo "等待 API 健康检查……"
for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "砚台已启动：http://localhost:3000"
    if command -v open >/dev/null 2>&1; then
      open "http://localhost:3000"
    fi
    exit 0
  fi
  sleep 2
done

echo "API 启动超时，查看日志："
docker compose logs --tail=100 api worker
exit 1
