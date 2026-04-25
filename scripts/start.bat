@echo off
title VEGA AI
color 0A

REM Change to project root (parent of scripts\)
cd /d "%~dp0.."
set "VEGA_ROOT=%CD%"

echo.
echo   V   V  EEEEE  GGGG   AAA
echo   V   V  E      G      A   A
echo   V   V  EEEE   G  GG  AAAAA
echo    V V   E      G   G  A   A
echo     V    EEEEE  GGGG   A   A
echo.
echo   Starting from: %VEGA_ROOT%
echo.

REM Create venv if missing
if not exist "%VEGA_ROOT%\venv\Scripts\activate.bat" (
    echo   [..] Creating virtual environment...
    python -m venv "%VEGA_ROOT%\venv"
    if errorlevel 1 (
        echo   [ERROR] Could not create venv
        pause
        exit /b 1
    )
)

REM Activate venv
call "%VEGA_ROOT%\venv\Scripts\activate.bat"
echo   [OK] Virtual environment ready

REM Check if packages installed by testing pyyaml
python -c "import yaml" >nul 2>&1
if errorlevel 1 (
    echo   [..] First run - installing packages...
    echo.
    pip install pyyaml >nul 2>&1 && echo   [OK] pyyaml || echo   [!!] pyyaml
    pip install structlog >nul 2>&1 && echo   [OK] structlog || echo   [!!] structlog
    pip install fastapi >nul 2>&1 && echo   [OK] fastapi || echo   [!!] fastapi
    pip install uvicorn >nul 2>&1 && echo   [OK] uvicorn || echo   [!!] uvicorn
    pip install "httpx>=0.27.0,<0.28.0" >nul 2>&1 && echo   [OK] httpx || echo   [!!] httpx
    pip install ollama >nul 2>&1 && echo   [OK] ollama || echo   [!!] ollama
    pip install pydantic >nul 2>&1 && echo   [OK] pydantic || echo   [!!] pydantic
    pip install jinja2 >nul 2>&1 && echo   [OK] jinja2 || echo   [!!] jinja2
    pip install aiofiles >nul 2>&1 && echo   [OK] aiofiles || echo   [!!] aiofiles
    pip install psutil >nul 2>&1 && echo   [OK] psutil || echo   [!!] psutil
    pip install networkx >nul 2>&1 && echo   [OK] networkx || echo   [!!] networkx
    pip install pyautogui >nul 2>&1 && echo   [OK] pyautogui || echo   [!!] pyautogui
    pip install Pillow >nul 2>&1 && echo   [OK] Pillow || echo   [!!] Pillow
    pip install mss >nul 2>&1 && echo   [OK] mss || echo   [!!] mss
    pip install apscheduler >nul 2>&1 && echo   [OK] apscheduler || echo   [!!] apscheduler
    pip install watchdog >nul 2>&1 && echo   [OK] watchdog || echo   [!!] watchdog
    pip install aiohttp >nul 2>&1 && echo   [OK] aiohttp || echo   [!!] aiohttp
    pip install numpy >nul 2>&1 && echo   [OK] numpy || echo   [!!] numpy
    pip install python-dotenv >nul 2>&1 && echo   [OK] dotenv || echo   [!!] dotenv
    pip install pyperclip >nul 2>&1 && echo   [OK] pyperclip || echo   [!!] pyperclip
    pip install websockets >nul 2>&1 && echo   [OK] websockets || echo   [!!] websockets
    echo.
    echo   [OK] All packages installed
    echo.
)

REM Load .env if exists
if exist "%VEGA_ROOT%\.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%VEGA_ROOT%\.env") do (
        set "%%a=%%b"
    )
)

echo   Launching VEGA...
echo.
python "%VEGA_ROOT%\main.py"

if errorlevel 1 (
    echo.
    echo   [ERROR] VEGA crashed. Check logs\vega.log
)
pause
