@echo off
rem ===================================================================
rem  One-click dev launcher for customer-service-backend
rem  Starts: AI backend :18082  +  frontend dev :5173
rem
rem  Usage: double-click, or pass an argument:
rem    start-dev.bat --init-db    create database + tables, then start
rem    start-dev.bat --status     show port status only
rem    start-dev.bat --stop       stop both services
rem
rem  NOTE: this file is intentionally pure ASCII so that cmd.exe never
rem  mangles it. All Chinese output comes from tools\dev_up.py.
rem ===================================================================
chcp 65001 >nul
cd /d "%~dp0"

rem --- Only pause when launched by double-click; a terminal run returns cleanly ---
rem     Double-click  -> %cmdcmdline% looks like: cmd /c ""D:\...\start-dev.bat" "
rem     Terminal run  -> %cmdcmdline% is just:    "C:\Windows\system32\cmd.exe"
set "PAUSEME=0"
echo %cmdcmdline% | find /i "%~nx0" >nul 2>nul
if not errorlevel 1 set "PAUSEME=1"

where uv >nul 2>nul
if errorlevel 1 (
  echo [ERROR] "uv" not found in PATH.
  echo         Install uv first: https://docs.astral.sh/uv/
  echo         Or just run:  uv run python tools\dev_up.py
  echo.
  if "%PAUSEME%"=="1" pause
  exit /b 1
)

uv run python "tools\dev_up.py" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo [ERROR] launcher exited with code %RC%
if "%PAUSEME%"=="1" pause
exit /b %RC%
