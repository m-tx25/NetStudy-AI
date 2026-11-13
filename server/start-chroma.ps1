# 启动本地 ChromaDB 服务（Windows）
#
# 为什么用它：嵌入式模式下后端与重索引脚本共用一份 SQLite，
# 两个进程同时写会让 chromadb 的 compactor 永久卡死
# （Error in compaction: Failed to apply logs to the metadata segment）。
# 起成独立服务后，只有这个进程写文件，后端/脚本都只是 HTTP 客户端。
#
# 用法（在 server/ 目录）：
#   .\start-chroma.ps1                    # 默认端口 8000，数据在 data/chroma_db
#   .\start-chroma.ps1 -Port 8001
#   .\start-chroma.ps1 -Rebuild           # 先备份并删掉旧数据（卡死后重建用）
#
# 启动后，在 server/.env 里设置：
#   CHROMA_HOST=127.0.0.1
#   CHROMA_PORT=8000
# 这样后端与脚本都会走服务模式。

param(
    [int]$Port = 8000,
    [string]$DataDir = './data/chroma_db',
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$chromaExe = Join-Path $PSScriptRoot '.venv\Scripts\chroma.exe'
if (-not (Test-Path $chromaExe)) {
    throw "未找到 chroma 可执行文件：$chromaExe`n请先在 server 目录安装依赖（pip install -r requirements.txt）"
}

# 解析成绝对路径
$dataPath = (Resolve-Path -LiteralPath '.').Path + '\' + ($DataDir -replace '^\./','' -replace '^\.\\','')
$dataPath = [System.IO.Path]::GetFullPath($dataPath)

if ($Rebuild -and (Test-Path $dataPath)) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $bak = "$dataPath.corrupt-$stamp"
    Rename-Item -LiteralPath $dataPath -NewName "chroma_db.corrupt-$stamp"
    Write-Host "[chroma] 旧数据已备份为 chroma_db.corrupt-$stamp" -ForegroundColor Yellow
}

if (-not (Test-Path $dataPath)) {
    New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
}

# 端口占用检查
$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    throw "端口 $Port 已被占用（PID $($inUse[0].OwningProcess)）。换一个端口：.\start-chroma.ps1 -Port $($Port+1)"
}

Write-Host "[chroma] 数据目录：$dataPath" -ForegroundColor Cyan
Write-Host "[chroma] 监听：http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "[chroma] 请把 server/.env 设为：CHROMA_HOST=127.0.0.1  CHROMA_PORT=$Port" -ForegroundColor Yellow
Write-Host '[chroma] 按 Ctrl+C 停止' -ForegroundColor Yellow
Write-Host ''

& $chromaExe run --path $dataPath --port $Port
