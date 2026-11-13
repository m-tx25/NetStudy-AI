@echo off
REM ===================================================================
REM  启动本地 ChromaDB 服务（Windows 批处理包装器）
REM
REM  为什么需要它：Windows 默认执行策略会拦截 .ps1（PSSecurityException
REM  「未对文件进行数字签名」）。这个 .cmd 用 -ExecutionPolicy Bypass
REM  只对本次调用放开，不修改系统全局设置。
REM
REM  用法：
REM    start-chroma.cmd                 默认 8000 端口
REM    start-chroma.cmd -Port 8001
REM    start-chroma.cmd -Rebuild        先备份并重建（向量库卡死后用）
REM  也可以直接双击运行（默认参数）。
REM ===================================================================
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\chroma.exe" (
    echo [错误] 未找到 .venv\Scripts\chroma.exe
    echo        请先在 server 目录安装依赖： .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-chroma.ps1" %*
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
    echo.
    echo [退出码 %EXITCODE%] 启动失败，请把上面的报错发出来。
    pause
)
endlocal & exit /b %EXITCODE%
