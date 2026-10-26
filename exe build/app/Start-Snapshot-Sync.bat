@echo off
setlocal
cd /d "%~dp0"
echo Enter your Heroes WoW installation folder (the folder containing WTF and Logs).
set /p "WOW_DIR=WoW folder: "
if not defined WOW_DIR exit /b 1
py -3 snapshot_sync.py --wow "%WOW_DIR%" --watch || python snapshot_sync.py --wow "%WOW_DIR%" --watch
pause
