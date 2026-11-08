@echo off
cd /d "%~dp0"
title Binance Futures 10x Trade Bot (7/24 Kesintisiz Calisiyor)
color 0A

echo =======================================================================
echo     BINANCE FUTURES 10X MULTI-AGENT TRADE BOT (7/24 AKTIF)
echo =======================================================================
echo.
echo Bot baslatiliyor... Telegram bildirimleri aktif.
echo Bilgisayarin uykuya gecmesi otomatik olarak engellenmistir.
echo.

:LOOP
python main.py
echo.
echo [UYARI] Bot beklenmedik sekilde durdu. 5 saniye icinde otomatik yeniden baslatiliyor...
timeout /t 5
goto LOOP
