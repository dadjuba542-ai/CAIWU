$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

docker compose down
Write-Host "砚台本地服务已停止。数据卷未删除，下次仍可继续使用。"
