@echo off
cd /d "%~dp0"
title Binance Futures AI Terminal
color 0B

echo =======================================================================
echo        BINANCE FUTURES AI TEK EKRAN CANLI TERMINAL
echo =======================================================================
echo.
echo Terminal baslatiliyor...
echo.

:: Arka planda sunucuyu ayaga kaldir
start /B python dashboard.py

:: 2 saniye bekle ve uygulama modunda ac
timeout /t 2 >nul
start msedge --app=http://127.0.0.1:5000 || start chrome --app=http://127.0.0.1:5000 || start http://127.0.0.1:5000

echo Terminal aktif. Kapatmak icin bu pencereyi kapatabilirsiniz.
pause
