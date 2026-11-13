@echo off
REM ===================================================================
REM  本机开发一键启动：Chroma 服务 + 后端
REM
REM  只需在 server 目录执行：
REM      dev.cmd
REM      dev.cmd --reindex   # 额外重建向量索引（换过 embedding Key、库损坏时用）
REM
REM  它会：
REM    1. 若 8000 端口没在监听，则在后台拉起 Chroma 服务
REM    2. 等端口就绪（最多 30 秒），失败会打印日志位置
REM    3. 前台启动后端（Ctrl+C 停止，随后会自动结束 Chroma）
REM
REM  Chroma 的输出写到 data\chroma.log，启动失败时看这个文件。
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CHROMA_PORT=8000"
set "BACKEND_PORT=3000"
set "CHROMA_EXE=%~dp0.venv\Scripts\chroma.exe"
set "PY=%~dp0.venv\Scripts\python.exe"
set "DATA_DIR=%~dp0data\chroma_db"
set "CHROMA_LOG=%~dp0data\chroma.log"

if not exist "%CHROMA_EXE%" (
    echo [错误] 未找到 chroma.exe：%CHROMA_EXE%
    echo        请先在 server 目录安装依赖
    pause
    exit /b 1
)
if not exist "%~dp0data" mkdir "%~dp0data"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

REM ---------- 1) Chroma 是否已在跑 ----------
netstat -ano | findstr ":%CHROMA_PORT% " | findstr LISTENING >nul
if not errorlevel 1 (
    echo [dev] Chroma 已在 %CHROMA_PORT% 端口运行，跳过启动
    goto backend
)

echo [dev] 启动 Chroma 服务（日志：data\chroma.log）...
start "chroma" /b "%CHROMA_EXE%" run --path "%DATA_DIR%" --port %CHROMA_PORT% > "%CHROMA_LOG%" 2>&1

set /a tries=0
:waitloop
netstat -ano | findstr ":%CHROMA_PORT% " | findstr LISTENING >nul
if not errorlevel 1 goto chroma_ok
set /a tries+=1
if !tries! geq 30 goto chroma_fail
timeout /t 1 >nul
goto waitloop

:chroma_fail
echo.
echo [dev] ✗ Chroma 启动失败（等了 30 秒端口未就绪）
echo       请把下面这个文件的最后 30 行发出来：
echo       %CHROMA_LOG%
echo.
echo ------ 日志尾部 ------
powershell -NoProfile -Command "Get-Content -LiteralPath '%CHROMA_LOG%' -Tail 30 -ErrorAction SilentlyContinue"
echo ----------------------
echo.
pause
exit /b 1

:chroma_ok
echo [dev] ✓ Chroma 就绪：http://127.0.0.1:%CHROMA_PORT%

:backend
if /i "%~1"=="--reindex" (
    echo [dev] 重建向量索引（会调用 embedding 接口，几分钟，请稍等）...
    echo.
    "%PY%" reindex_all.py
    if errorlevel 1 (
        echo.
        echo [dev] ✗ 重建索引失败，请把上面的输出发出来
        pause
        exit /b 1
    )
    echo.
)

echo [dev] 启动后端：http://127.0.0.1:%BACKEND_PORT%/api
echo [dev] 验证地址：http://127.0.0.1:%BACKEND_PORT%/api/health
echo [dev] 按 Ctrl+C 停止后端
echo.

"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT%
set "RC=%ERRORLEVEL%"

echo.
echo [dev] 后端已退出（代码 %RC%）
if /i "%RC%"=="0" goto cleanup

:cleanup
echo [dev] 结束 Chroma 服务
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%CHROMA_PORT% " ^| findstr LISTENING') do (
    taskkill /F /PID %%P >nul 2>&1
)
endlocal
exit /b %RC%
