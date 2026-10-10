@echo off
setlocal
title Bagua Backend

rem ============================================================
rem  Bagua backend launcher -- ASCII only + CRLF on purpose.
rem
rem  cmd.exe traps deliberately avoided here:
rem   1) Non-ASCII text in a .bat gets mangled because cmd reads
rem      the file in the ANSI codepage, and the mangled fragments
rem      were then EXECUTED as commands - which ate the "cd" line,
rem      made uvicorn start from the repo root, fail with
rem      "Could not import module main", and close the window.
rem   2) An unescaped parenthesis inside an "if (...)" block breaks
rem      block parsing and silently swallows the echo lines above it.
rem      So: no round brackets in any echo text below.
rem
rem  Why no --reload by default: more than one agent session edits this
rem  repo at the same time. WatchFiles then reloads - or dies - in the
rem  middle of serving. Restart this window after code changes.
rem  Want live reload anyway: add --reload to the uvicorn line.
rem ============================================================

cd /d "%~dp0backend"

if not exist "main.py" (
  echo [ERROR] main.py not found in "%CD%"
  echo         Run this from the repo root: D:\Web\bagua\start_backend.bat
  pause
  exit /b 1
)

:loop

rem --- Step 1: is a backend already answering?  0 = yes, 1 = no ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 'http://127.0.0.1:8000/api/health'; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo [SKIP] a backend is ALREADY running and healthy - nothing to start.
  echo.
  echo   health : http://127.0.0.1:8000/api/health
  echo   site   : http://localhost:3000   -- start it with start_frontend.bat
  echo.
  echo   If that backend is not yours - e.g. another session started it -
  echo   find the owner with:  netstat -ano ^| findstr :8000
  pause
  exit /b 0
)

rem --- Step 2: port held by a process that is not answering? ---
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [ERROR] port 8000 is held by a process that does not answer /api/health.
  echo         Find it with:  netstat -ano ^| findstr :8000
  echo         Kill just it:  taskkill /F /PID ^<pid^>
  echo.
  netstat -ano | findstr /R /C:":8000 .*LISTENING"
  pause
  exit /b 1
)

echo Starting Bagua backend - FastAPI / uvicorn ...
echo.
echo   local  : http://127.0.0.1:8000
echo   LAN    : http://%COMPUTERNAME%:8000   -- also via Radmin / Tailscale IP
echo   health : http://127.0.0.1:8000/api/health
echo.
echo NOTE: --host 0.0.0.0 exposes port 8000 to LAN and VPN peers.
echo       For public hosting bind 127.0.0.1 and put nginx in front.
echo.

rem --no-proxy-headers is REQUIRED here: uvicorn trusts X-Forwarded-For by
rem default via --proxy-headers, so a forged XFF would bypass the per-IP
rem rate limit. Verified: 70 forged IPs gave zero 429s without this flag,
rem and correct 429s with it.
rem Extra check available: python tools/selfcheck.py
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
set RC=%ERRORLEVEL%

if "%RC%"=="0" goto done

echo.
echo [STOPPED] uvicorn exited abnormally, code %RC%.
echo Checking whether another backend took over port 8000 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 'http://127.0.0.1:8000/api/health'; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto taken

echo Port is still free - restarting in 3 seconds. Press Ctrl+C to stop for good.
ping -n 4 127.0.0.1 >nul
goto loop

:taken
echo.
echo [SKIP] another backend is answering on port 8000 now - this window stops.
echo        health : http://127.0.0.1:8000/api/health
pause
exit /b 0

:done
echo.
echo [STOPPED] uvicorn exited normally, code 0.
pause
