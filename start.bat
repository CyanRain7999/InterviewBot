@echo off
setlocal
title Interview Assistant
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PY=%ROOT%\.venv\Scripts\python.exe"
set "MAIN=%ROOT%\inter\main.py"
set "ASR=%ROOT%\inter\asr_server.py"
set "CONFIG=%ROOT%\inter\config\config.json"

echo ==========================================
echo   Interview Assistant (InterviewBot)
echo ==========================================
echo.

if not exist "%PY%" (
    echo [ERROR] Python venv not found:
    echo        %PY%
    echo.
    echo        Create it first:
    echo          python -m venv .venv
    echo          .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%MAIN%" (
    echo [ERROR] main.py not found:
    echo        %MAIN%
    pause
    exit /b 1
)

set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem ---- Start the persistent Whisper ASR server only when ASR_PROVIDER=whisper ----
set "PROVIDER=baidu"
if exist "%CONFIG%" (
    findstr /c:"ASR_PROVIDER" "%CONFIG%" | findstr /i /c:"whisper" >nul 2>&1
    if not errorlevel 1 set "PROVIDER=whisper"
)

if /i "%PROVIDER%"=="whisper" (
    echo [INFO] Starting local Whisper ASR server (first model load may take a while)...
    start "ASR Server" /min "%PY%" "%ASR%"

    echo [INFO] Waiting for the ASR server to be ready...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 120;$i++){ try { $r=Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 2; if($r.ready -eq $true){ $ok=$true; break } } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){ exit 1 }"
    if errorlevel 1 (
        echo [WARN] ASR server was not ready in time. Voice features may be unavailable.
        echo        The app will still start.
    ) else (
        echo [INFO] ASR server is ready.
    )
)

echo.
echo [INFO] Starting Interview Assistant...
cd /d "%ROOT%\inter"
"%PY%" "%MAIN%"

echo.
echo ==========================================
echo Interview Assistant exited.
echo ==========================================

if /i "%PROVIDER%"=="whisper" (
    echo [INFO] Shutting down the ASR server...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*asr_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
)

pause
endlocal
