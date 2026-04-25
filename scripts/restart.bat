@echo off
echo Stopping VEGA server...
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM python3.exe /T 2>nul
timeout /t 2 /nobreak >nul
echo Starting VEGA server...
cd /d "%~dp0.."
call venv\Scripts\activate.bat
start "VEGA AI" python main.py
echo.
echo VEGA restarted! Open http://localhost:8888 in your browser.
