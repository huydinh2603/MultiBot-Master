@echo off
chcp 65001 >nul
title Discord Widget - Local Rich Presence
cd /d "%~dp0bots\widget"

echo ===================================================
echo     DISCORD WIDGET - LOCAL RICH PRESENCE 24/7
echo ===================================================
echo.
echo [1/2] Đang kiểm tra thư viện...
if not exist "node_modules" (
    echo Đang cài đặt thư viện cần thiết lần đầu...
    call npm install
)

echo [2/2] Đang khởi động Discord Widget trên máy tính...
echo Giao diện điều khiển sẽ tự động mở tại: http://localhost:3000
echo.
echo * Mẹo: Để widget chạy ngầm không hiện cửa sổ này, hãy chạy file Start_Widget_Silent.vbs
echo.

start http://localhost:3000
node index.js
pause
