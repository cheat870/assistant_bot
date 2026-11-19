@echo off
echo Stopping Telegram Assistant Bot...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *Telegram Assistant Bot*" 2>nul
taskkill /F /FI "COMMANDLINE eq *telegram_assistant_bot\main.py*" 2>nul
wmic process where "commandline like '%%telegram_assistant_bot\\main.py%%'" delete 2>nul
echo Bot stopped successfully.
pause
