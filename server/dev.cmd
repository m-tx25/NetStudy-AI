@echo off
REM ===================================================================
REM  Local dev launcher: Chroma service + backend
REM
REM  Usage (run inside the server directory):
REM      dev.cmd                        start only (Chroma + backend)
REM      dev.cmd --reindex              rebuild vector index before start
REM      dev.cmd --rebuild              backup the old vector DB, start fresh
REM      dev.cmd --rebuild --reindex    one-shot recovery after index damage
REM
REM  When to use --rebuild:
REM      Logs show "Error loading hnsw index" or "Error in compaction".
REM      That means the vector index is corrupted: writing into it keeps
REM      failing, so you must start from an empty DB.
REM
REM  NOTE: this file is intentionally ASCII-only. cmd.exe reads .cmd with
REM  the OEM code page (GBK on zh-CN), so UTF-8 Chinese would be decoded
REM  as mojibake and could split lines into bogus commands.
REM
REM  Chroma output goes to data\chroma.log; on startup failure the tail
REM  of that log is printed automatically.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CHROMA_PORT=8000"
set "BACKEND_PORT=3000"
set "CHROMA_EXE=%~dp0.venv\Scripts\chroma.exe"
set "PY=%~dp0.venv\Scripts\python.exe"
set "DATA_DIR=%~dp0data\chroma_db"
set "CHROMA_LOG=%~dp0data\chroma.log"

set "DO_REINDEX="
set "DO_REBUILD="
for %%A in (%*) do (
    if /i "%%A"=="--reindex" set "DO_REINDEX=1"
    if /i "%%A"=="--rebuild" set "DO_REBUILD=1"
)

if not exist "%CHROMA_EXE%" (
    echo [dev] ERROR: chroma.exe not found: %CHROMA_EXE%
    echo [dev] Run pip install -r requirements.txt in server/ first.
    pause
    exit /b 1
)
if not exist "%~dp0data" mkdir "%~dp0data"

REM ---------- 0) optional: back up and drop the old vector DB ----------
if defined DO_REBUILD (
    if exist "%DATA_DIR%" (
        for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%T"
        echo [dev] Backing up old vector DB to chroma_db.broken-!STAMP!
        move "%DATA_DIR%" "%DATA_DIR%.broken-!STAMP!" >nul
    )
)
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

REM ---------- 1) is Chroma already running? ----------
netstat -ano | findstr ":%CHROMA_PORT% " | findstr LISTENING >nul
if not errorlevel 1 (
    echo [dev] Chroma already listening on %CHROMA_PORT%, skip start
    goto maybe_reindex
)

echo [dev] Starting Chroma (log: data\chroma.log) ...
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
echo [dev] FAILED: Chroma did not listen on %CHROMA_PORT% within 30s.
echo [dev] Please send the tail of: %CHROMA_LOG%
echo.
echo ------ log tail ------
powershell -NoProfile -Command "Get-Content -LiteralPath '%CHROMA_LOG%' -Tail 30 -ErrorAction SilentlyContinue"
echo ----------------------
echo.
pause
exit /b 1

:chroma_ok
echo [dev] Chroma ready: http://127.0.0.1:%CHROMA_PORT%

:maybe_reindex
if not defined DO_REINDEX goto backend

echo.
echo [dev] Rebuilding vector index (calls embedding API, may take minutes) ...
"%PY%" reindex_all.py
if errorlevel 1 (
    echo.
    echo [dev] FAILED: reindex failed, please send the output above.
    echo [dev] If it says "Error loading hnsw index", run: dev.cmd --rebuild --reindex
    pause
    exit /b 1
)
echo.

:backend
echo [dev] Starting backend: http://127.0.0.1:%BACKEND_PORT%/api
echo [dev] Health check: http://127.0.0.1:%BACKEND_PORT%/api/health
echo [dev] Press Ctrl+C to stop
echo.

"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT%
set "RC=%ERRORLEVEL%"

echo.
echo [dev] Backend exited with code %RC%
echo [dev] Stopping Chroma
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%CHROMA_PORT% " ^| findstr LISTENING') do (
    taskkill /F /PID %%P >nul 2>&1
)
endlocal
exit /b %RC%
