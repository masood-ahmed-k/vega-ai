@echo off
title VEGA AI - Full Auto Install
color 0A

REM Change to project root (parent of scripts\)
cd /d "%~dp0.."
set "VEGA_ROOT=%CD%"

echo.
echo   ======================================
echo        VEGA AI - Auto Installer
echo   ======================================
echo.
echo   Folder: %VEGA_ROOT%
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python not found!
    echo   Get it from https://python.org
    pause
    exit /b 1
)
echo   [1/4] Python found

REM Create venv
echo   [2/4] Creating virtual environment...
if exist "%VEGA_ROOT%\venv" (
    echo   venv already exists, reusing it
) else (
    python -m venv "%VEGA_ROOT%\venv"
)
call "%VEGA_ROOT%\venv\Scripts\activate.bat"

REM Upgrade pip first
echo   [3/4] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

REM Install packages one by one so failures dont block everything
echo   [4/4] Installing packages (this takes 1-2 minutes)...
echo.

pip install pyyaml >nul 2>&1 && echo   [OK] pyyaml || echo   [SKIP] pyyaml
pip install structlog >nul 2>&1 && echo   [OK] structlog || echo   [SKIP] structlog
pip install fastapi >nul 2>&1 && echo   [OK] fastapi || echo   [SKIP] fastapi
pip install uvicorn >nul 2>&1 && echo   [OK] uvicorn || echo   [SKIP] uvicorn
pip install "httpx>=0.27.0,<0.28.0" >nul 2>&1 && echo   [OK] httpx || echo   [SKIP] httpx
pip install ollama >nul 2>&1 && echo   [OK] ollama || echo   [SKIP] ollama
pip install pydantic >nul 2>&1 && echo   [OK] pydantic || echo   [SKIP] pydantic
pip install jinja2 >nul 2>&1 && echo   [OK] jinja2 || echo   [SKIP] jinja2
pip install aiofiles >nul 2>&1 && echo   [OK] aiofiles || echo   [SKIP] aiofiles
pip install psutil >nul 2>&1 && echo   [OK] psutil || echo   [SKIP] psutil
pip install networkx >nul 2>&1 && echo   [OK] networkx || echo   [SKIP] networkx
pip install pyautogui >nul 2>&1 && echo   [OK] pyautogui || echo   [SKIP] pyautogui
pip install Pillow >nul 2>&1 && echo   [OK] Pillow || echo   [SKIP] Pillow
pip install mss >nul 2>&1 && echo   [OK] mss || echo   [SKIP] mss
pip install apscheduler >nul 2>&1 && echo   [OK] apscheduler || echo   [SKIP] apscheduler
pip install watchdog >nul 2>&1 && echo   [OK] watchdog || echo   [SKIP] watchdog
pip install aiohttp >nul 2>&1 && echo   [OK] aiohttp || echo   [SKIP] aiohttp
pip install numpy >nul 2>&1 && echo   [OK] numpy || echo   [SKIP] numpy
pip install python-dotenv >nul 2>&1 && echo   [OK] python-dotenv || echo   [SKIP] python-dotenv
pip install pyperclip >nul 2>&1 && echo   [OK] pyperclip || echo   [SKIP] pyperclip
pip install websockets >nul 2>&1 && echo   [OK] websockets || echo   [SKIP] websockets

echo.
echo   ======================================
echo        INSTALLATION COMPLETE
echo.
echo   Next steps:
echo     1. Install Ollama from https://ollama.com
echo     2. Run: ollama pull qwen3:8b
echo     3. Double-click scripts\start.bat
echo   ======================================
echo.
pause
