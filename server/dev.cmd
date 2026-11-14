@echo off
REM ===================================================================
REM  Local dev launcher: Chroma service + backend
REM
REM  Usage (run inside the server directory):
REM      dev.cmd                        start only (Chroma + backend)
REM      dev.cmd --stop                 SAFE shutdown: backend -> wait -> Chroma
REM      dev.cmd --check                health check only, do not start
REM      dev.cmd --reindex              rebuild vector index before start
REM      dev.cmd --rebuild              backup the old vector DB, start fresh
REM      dev.cmd --rebuild --reindex    one-shot recovery after index damage
REM      dev.cmd --restore              restore the last good snapshot
REM      dev.cmd --snapshot             copy current DB to the snapshot slot
REM
REM  Why the index keeps getting damaged (read this before killing things):
REM    1. Chroma writes sqlite rows FIRST, HNSW index files SECOND.
REM       Force-killing it (taskkill /F, Task Manager, power loss) between the
REM       two steps leaves vectors in sqlite but no *.bin index files, and
REM       every later query fails with "Error loading hnsw index".
REM       That state cannot be repaired by writing more data.
REM    2. Two Chroma processes on the same data dir WILL corrupt it.
REM    3. The system proxy (Clash) can hijack 127.0.0.1:8000 and return 502,
REM       which looks like corruption but is not (see docs/vectorstore.md).
REM
REM  The danger window is ONLY while writes are in flight (upload / reindex).
REM  An idle Chroma can be closed any way you like.
REM
REM  This script therefore:
REM    - --stop waits for the backend to exit, then 10s for Chroma to flush;
REM    - keeps a snapshot after every successful reindex;
REM    - refuses to start a second instance on the same port.
REM
REM  NOTE: this file is intentionally ASCII-only. cmd.exe reads .cmd with
REM  the OEM code page (GBK on zh-CN), so UTF-8 Chinese would be decoded
REM  as mojibake and could split lines into bogus commands.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CHROMA_PORT=8000"
set "BACKEND_PORT=3000"
set "CHROMA_EXE=%~dp0.venv\Scripts\chroma.exe"
set "PY=%~dp0.venv\Scripts\python.exe"
set "DATA_DIR=%~dp0data\chroma_db"
set "SNAP_DIR=%~dp0data\chroma_db.snapshot"
set "CHROMA_LOG=%~dp0data\chroma.log"

set "DO_REINDEX="
set "DO_REBUILD="
set "DO_RESTORE="
set "DO_SNAPSHOT="
set "DO_CHECK="
set "DO_STOP="
for %%A in (%*) do (
    if /i "%%A"=="--reindex" set "DO_REINDEX=1"
    if /i "%%A"=="--rebuild" set "DO_REBUILD=1"
    if /i "%%A"=="--restore" set "DO_RESTORE=1"
    if /i "%%A"=="--snapshot" set "DO_SNAPSHOT=1"
    if /i "%%A"=="--check" set "DO_CHECK=1"
    if /i "%%A"=="--stop" set "DO_STOP=1"
)

if not exist "%CHROMA_EXE%" (
    echo [dev] ERROR: chroma.exe not found: %CHROMA_EXE%
    echo [dev] Run pip install -r requirements.txt in server/ first.
    pause
    exit /b 1
)
if not exist "%~dp0data" mkdir "%~dp0data"

REM ---------- 0aa) SAFE shutdown ----------
if defined DO_STOP (
    echo [dev] Stopping backend on port %BACKEND_PORT% ...
    call :stop_port %BACKEND_PORT%
    echo [dev] Waiting 10s for Chroma to flush pending writes ...
    "%PY%" -c "import time;time.sleep(10)" >nul 2>&1
    echo [dev] Stopping Chroma on port %CHROMA_PORT% ...
    call :stop_port %CHROMA_PORT%
    echo.
    echo [dev] Stopped safely. Pending writes are flushed.
    echo [dev] Tip: run "dev.cmd --check" if you want to verify DB health.
    exit /b 0
)

REM ---------- 0a) health check only ----------
if defined DO_CHECK (
    echo [dev] Running vector store check ...
    "%PY%" check_chroma.py
    set "RC=!ERRORLEVEL!"
    echo.
    pause
    exit /b !RC!
)

REM ---------- 0b) restore snapshot ----------
if defined DO_RESTORE (
    if not exist "%SNAP_DIR%" (
        echo [dev] ERROR: no snapshot at %SNAP_DIR%
        echo [dev] Create one with: dev.cmd --snapshot
        pause
        exit /b 1
    )
    netstat -ano | findstr ":%CHROMA_PORT% " | findstr LISTENING >nul
    if not errorlevel 1 (
        echo [dev] ERROR: Chroma is running. Run "dev.cmd --stop" first.
        pause
        exit /b 1
    )
    for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%T"
    if exist "%DATA_DIR%" (
        echo [dev] Moving broken DB to chroma_db.broken-!STAMP!
        move "%DATA_DIR%" "%DATA_DIR%.broken-!STAMP!" >nul
    )
    echo [dev] Restoring snapshot ...
    robocopy "%SNAP_DIR%" "%DATA_DIR%" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul
    echo [dev] Restored. Starting with existing vectors.
    set "DO_REBUILD="
    set "DO_REINDEX="
)

REM ---------- 0c) optional: back up and drop the old vector DB ----------
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
"%PY%" -c "import time;time.sleep(1)" >nul 2>&1
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
if not defined DO_REINDEX goto maybe_snapshot

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
echo [dev] Reindex OK. Taking a snapshot so a future corruption is cheap to undo ...
set "DO_SNAPSHOT=1"
echo.

:maybe_snapshot
if not defined DO_SNAPSHOT goto backend

if exist "%SNAP_DIR%" rd /s /q "%SNAP_DIR%"
echo [dev] Snapshot: %SNAP_DIR%
robocopy "%DATA_DIR%" "%SNAP_DIR%" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul
if errorlevel 8 (
    echo [dev] WARNING: snapshot copy reported errors, continue anyway
) else (
    echo [dev] Snapshot saved.
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
echo [dev] Waiting 8s so Chroma can flush pending writes to disk ...
"%PY%" -c "import time;time.sleep(8)" >nul 2>&1
echo [dev] Stopping Chroma
call :stop_port %CHROMA_PORT%
echo [dev] Done.
endlocal
exit /b %RC%

REM -------------------------------------------------------------------
REM  :stop_port <port>
REM  Look the PID up once, try a normal terminate, then force it.
REM  Deliberately avoids a per-second netstat poll: netstat is slow here
REM  (a 15-round poll took 279 seconds once, which is unusable).
REM -------------------------------------------------------------------
:stop_port
set "SPORT=%~1"
set "SPID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%SPORT% " ^| findstr LISTENING') do set "SPID=%%P"
if not defined SPID (
    echo [dev] Port %SPORT% already free
    exit /b 0
)
echo [dev] Stopping PID !SPID! on port %SPORT% ...
taskkill /PID !SPID! >nul 2>&1
"%PY%" -c "import time;time.sleep(1)" >nul 2>&1
netstat -ano | findstr ":%SPORT% " | findstr LISTENING >nul
if errorlevel 1 (
    echo [dev] Port %SPORT% free
    exit /b 0
)
echo [dev] Graceful stop did not work, forcing PID !SPID! ...
taskkill /F /PID !SPID! >nul 2>&1
"%PY%" -c "import time;time.sleep(2)" >nul 2>&1
netstat -ano | findstr ":%SPORT% " | findstr LISTENING >nul
if errorlevel 1 (
    echo [dev] Port %SPORT% free
) else (
    echo [dev] WARNING: port %SPORT% still busy
)
exit /b 0
