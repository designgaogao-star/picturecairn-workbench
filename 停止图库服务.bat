@echo off
chcp 65001 >nul
title 停止图库服务
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if($c){ $c.OwningProcess | Select-Object -Unique | ForEach-Object { try{ Stop-Process -Id $_ -Force; Write-Host ('已停止进程 PID '+$_) }catch{} }; Write-Host '图库服务已停止。' } else { Write-Host '图库服务当前未在运行。' }"
timeout /t 3 >nul
