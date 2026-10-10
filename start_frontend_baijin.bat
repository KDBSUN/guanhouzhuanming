@echo off
setlocal
title Bagua Frontend Baijin
cd /d "%~dp0frontend-baijin"

rem ============================================================
rem  Bagua frontend-baijin launcher -- ASCII only + CRLF on purpose.
rem
rem  cmd.exe traps avoided here, same as start_frontend.bat:
rem   1) Non-ASCII comments get read in the ANSI codepage and the
rem      mangled fragments can be EXECUTED as commands.
rem   2) An unescaped round bracket inside an "if (...)" block breaks
rem      block parsing and swallows the echo lines above it.
rem      So: no round brackets in any echo text below.
rem
rem  Ports: 3000 = old frontend, 3001 = this one, 8000 = backend.
rem  /api is proxied by vite to 127.0.0.1:8000, so the backend must
rem  be running for anything that needs data. Start it with
rem  start_backend.bat in the repo root.
rem ============================================================

if not exist "package.json" (
  echo [ERROR] package.json not found in "%CD%"
  echo         Expected layout: D:\Web\bagua\frontend-baijin\package.json
  pause
  exit /b 1
)

:loop
netstat -ano | findstr /R /C:":3001 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [SKIP] port 3001 is already in use - the dev server is probably running.
  echo.
  echo   site: http://localhost:3001
  pause
  exit /b 0
)

if not exist "node_modules" (
  echo node_modules missing - running npm install first ...
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
  )
)

rem --- backend check: only a warning, the UI degrades on its own ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 'http://127.0.0.1:8000/api/health'; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo [WARN] backend on port 8000 is not answering /api/health.
  echo        The page will load, but divination, records and the
  echo        almanac strip need it. Start it separately:
  echo          D:\Web\bagua\start_backend.bat
  echo.
)

echo Starting frontend-baijin - Vite dev server ...
echo.
echo   local : http://localhost:3001
echo   LAN   : http://%COMPUTERNAME%:3001   -- open this on your phone
echo.
echo   backend must be at http://127.0.0.1:8000   -- via vite proxy
echo.
echo Press Ctrl+C to stop. This window stays open on crash.
echo.

call npm run dev:host
set RC=%ERRORLEVEL%

echo.
echo [STOPPED] vite exited, code %RC%.
echo If that was not Ctrl+C, read the messages above.
pause
exit /b %RC%
