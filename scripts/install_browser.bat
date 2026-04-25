@echo off
REM VEGA AI — Browser Agent (Playwright)

cd /d "%~dp0.."

echo.
echo ============================================================
echo   VEGA AI — Browser Agent Dependencies
echo ============================================================
echo.
echo Installs Playwright + Chromium so VEGA can browse the web.
echo.
pause

python -m pip install playwright>=1.45.0
python -m playwright install chromium

echo.
echo [OK] Browser agent ready.
echo.
pause
