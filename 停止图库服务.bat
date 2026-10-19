@echo off
cd /d "%~dp0"
pwsh -NoProfile -File "%~dp0scripts\start.ps1" -Stop
