@echo off
chcp 65001 >nul

echo ============================================
echo   ETF Monitor - PyInstaller Build Script
echo ============================================
echo.

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "VENV_PIP=%SCRIPT_DIR%.venv\Scripts\pip.exe"

if exist "%VENV_PYTHON%" (
    echo [INFO] Using virtual environment: .venv
    set "PYTHON=%VENV_PYTHON%"
    set "PIP=%VENV_PIP%"
) else (
    echo [INFO] No venv found, using system Python
    set "PYTHON=python"
    set "PIP=pip"
)

"%PYTHON%" -c "import PyInstaller" 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Installing PyInstaller...
    "%PIP%" install pyinstaller
    if %errorlevel% neq 0 (
        echo [ERROR] PyInstaller install failed. Try: "%PIP%" install pyinstaller
        pause
        exit /b 1
    )
)

echo [INFO] Starting build...
echo.

if exist "dist\ETFMonitor.exe" del /f /q "dist\ETFMonitor.exe" 2>nul
if exist "build" rmdir /s /q "build" 2>nul

"%PYTHON%" -m PyInstaller --clean --noconfirm ETFMonitor.spec

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo   Build successful!
    echo   Output: dist\ETFMonitor.exe
    echo ============================================
) else (
    echo.
    echo [ERROR] Build failed. Check output above.
    echo [TIP] Try: "%PYTHON%" -m PyInstaller --onefile --windowed --name ETFMonitor main.py
)

pause
