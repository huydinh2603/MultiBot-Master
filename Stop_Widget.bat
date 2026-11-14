@echo off
chcp 65001 >nul
title Tắt Discord Widget
echo ===================================================
echo     ĐANG TẮT TIẾN TRÌNH DISCORD WIDGET...
echo ===================================================
echo.
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
    echo [OK] Đã tắt tiến trình Discord Widget (PID: %%a)
)
echo.
echo Đã dừng Discord Widget hoàn tất.
timeout /t 3 >nul
