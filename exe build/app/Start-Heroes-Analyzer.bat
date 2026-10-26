@echo off
setlocal
cd /d "%~dp0"
if not exist "wow_path.txt" (
  echo First run: enter the Heroes WoW installation directory ^(containing WTF and Logs^).
  set /p "WOW_DIR=WoW directory: "
  if not defined WOW_DIR goto launch
  setlocal enabledelayedexpansion
  >"wow_path.txt" echo(!WOW_DIR!
  endlocal
)
if exist "wow_path.txt" (
  set /p WOW_DIR=<"wow_path.txt"
  if defined WOW_DIR start "Heroes WoW Snapshot Auto Sync" /min cmd /k "py -3 snapshot_sync.py --wow ""%WOW_DIR%"" --watch || python snapshot_sync.py --wow ""%WOW_DIR%"" --watch"
)
:launch
py -3 server.py || python server.py
pause
