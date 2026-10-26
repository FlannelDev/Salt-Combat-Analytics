@echo off
    setlocal EnableExtensions
    cd /d "%~dp0"
    where py >nul 2>nul
    if errorlevel 1 (echo Python launcher not found. Install Python 3.11 or 3.12 x64. & pause & exit /b 1)
    py -3 -m venv .buildvenv
    if errorlevel 1 (echo Could not create virtual environment. & pause & exit /b 1)
    call ".buildvenv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto failed
    call ".buildvenv\Scripts\python.exe" -m pip install "pyinstaller>=6,<7"
    if errorlevel 1 goto failed
    call ".buildvenv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --console --name SaltCombatAnalytics --hidden-import snapshot_sync --distpath dist --workpath build launcher.py
    if errorlevel 1 goto failed
    xcopy "app\*" "dist\SaltCombatAnalytics\" /E /I /Y >nul
    if errorlevel 1 goto failed
    echo.
    echo BUILD COMPLETE: dist\SaltCombatAnalytics\SaltCombatAnalytics.exe
    echo Copy the WHOLE dist\SaltCombatAnalytics folder to your destination PC.
    pause
    exit /b 0
    :failed
    echo BUILD FAILED. Review the error above.
    pause
    exit /b 1
