@echo off
REM ===================================================================
REM  一键启动后端（Windows 批处理包装器）
REM
REM  为什么需要它：Windows 默认执行策略会拦截 .ps1
REM  （PSSecurityException「未对文件进行数字签名」）。这个 .cmd 用
REM  -ExecutionPolicy Bypass 只对本次调用放开，不改系统全局设置。
REM
REM  用法：
REM    start.cmd                默认 3000 端口 + 热重载
REM    start.cmd -Port 8000
REM    start.cmd -NoReload      关闭热重载
REM  也可以直接双击运行（默认参数）。
REM ===================================================================
setlocal
cd /d "%~dp0"

if not exist "%~dp0start.ps1" (
    echo [错误] 未找到 start.ps1
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
    echo.
    echo [退出码 %EXITCODE%] 启动失败，请把上面的报错发出来。
    pause
)
endlocal & exit /b %EXITCODE%
