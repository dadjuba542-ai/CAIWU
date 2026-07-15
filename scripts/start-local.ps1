$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未找到 Docker。请先安装并启动 Docker Desktop。"
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker 引擎没有运行。请先启动 Docker Desktop。"
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已从 .env.example 创建本地 .env。"
}

Write-Host "正在构建并启动砚台本地服务……"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose 启动失败。请执行 docker compose logs 查看日志。"
}

Write-Host "等待 API 健康检查……"
for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing
        if ($health.StatusCode -eq 200) {
            Write-Host "砚台已启动：http://localhost:3000"
            Start-Process "http://localhost:3000"
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Host "API 启动超时，正在打印日志："
docker compose logs --tail=100 api worker
exit 1
