@echo off
cd /d "%~dp0"
title Gallery Review - localhost:8765
set "PY312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY312%" (
  set "PY=%PY312%"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python was not found. Please install Python 3 + Pillow.
    pause
    exit /b
  )
  set "PY=python"
)
echo Starting gallery review server...
echo Browser will open automatically at http://127.0.0.1:8765
echo Keep this window open while reviewing. Press Ctrl+C to stop.
"%PY%" gallery_server.py
pause
