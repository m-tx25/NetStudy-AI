# 启动后端（FastAPI）。首次运行会自动创建虚拟环境并安装依赖。
#
#   .\start.ps1              # 监听 0.0.0.0:3000，热重载
#   .\start.ps1 -Port 8000   # 指定端口
#   .\start.ps1 -NoReload    # 关闭热重载（更省资源）
param(
    [int]$Port = 3000,
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host '[start] 未找到 .venv，正在创建虚拟环境…' -ForegroundColor Yellow
    $systemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $systemPython) { throw '未找到 python，请先安装 Python 3.11+ 并加入 PATH' }
    & $systemPython -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

if (-not (Test-Path (Join-Path $PSScriptRoot '.env'))) {
    Copy-Item (Join-Path $PSScriptRoot '.env.example') (Join-Path $PSScriptRoot '.env')
    Write-Host '[start] 已从 .env.example 生成 .env（MYSQL_PASSWORD 与 ZHIPUAI_API_KEY 需自行填写）' -ForegroundColor Yellow
}

# ---- 前置检查：把最容易卡住的两件事提前说清楚 ----
$envFile = Join-Path $PSScriptRoot '.env'
$envText = Get-Content $envFile -Raw -Encoding UTF8

function Get-EnvValue([string]$name) {
    $m = [regex]::Match($envText, "(?m)^\s*$name\s*=\s*(.*)$")
    if ($m.Success) { return $m.Groups[1].Value.Trim() } else { return '' }
}

# 1) MySQL：默认要求可连接。配置了 DATABASE_URL 指向 sqlite 时跳过。
$dsn = Get-EnvValue 'DATABASE_URL'
if ($dsn -like '*sqlite*') {
    Write-Host '[start] 检测到 DATABASE_URL 指向 SQLite（仅开发用），跳过 MySQL 检查' -ForegroundColor Yellow
} else {
    $dbHost = Get-EnvValue 'MYSQL_HOST'; if (-not $dbHost) { $dbHost = '127.0.0.1' }
    $dbPort = Get-EnvValue 'MYSQL_PORT'; if (-not $dbPort) { $dbPort = '3306' }
    $probe = Test-NetConnection -ComputerName $dbHost -Port ([int]$dbPort) -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
    if (-not $probe.TcpTestSucceeded) {
        Write-Host "[start] 警告：连不上 MySQL（$dbHost`:$dbPort）。" -ForegroundColor Red
        Write-Host '        后端启动会报「无法连接 MySQL」。任选一种方式准备数据库：' -ForegroundColor Yellow
        Write-Host '          docker compose up -d mysql redis   # 需 Docker，root 密码为 chuangzhibei'
        Write-Host '          https://dev.mysql.com/downloads/installer/   # 官方安装包'
        Write-Host '        或临时改用 SQLite（仅开发）：在 .env 中取消注释' -ForegroundColor Yellow
        Write-Host '          DATABASE_URL=sqlite+aiosqlite:///./data/app.db'
        Write-Host ''
    } else {
        Write-Host "[start] MySQL 可达：$dbHost`:$dbPort" -ForegroundColor Green
    }
}

# 2) 智谱向量化 Key：缺失不阻塞启动，但检索质量会下降
$zhipu = Get-EnvValue 'ZHIPUAI_API_KEY'
if (-not $zhipu) {
    Write-Host '[start] 提示：未配置 ZHIPUAI_API_KEY，向量化将退化为 Chroma 默认英文模型，' -ForegroundColor Yellow
    Write-Host '        中文检索效果一般。申请地址：https://open.bigmodel.cn/' -ForegroundColor Yellow
}

$uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', "$Port")
if (-not $NoReload) { $uvicornArgs += '--reload' }

Write-Host "[start] http://localhost:$Port  （接口文档 /docs）" -ForegroundColor Green
& $venvPython @uvicornArgs
