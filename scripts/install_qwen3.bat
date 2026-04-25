@echo off
REM VEGA AI — Qwen3 Model Installer
REM Downloads all 3 Qwen3 models for VEGA (strong + balanced + fast)
REM
REM Requires: Ollama installed and running (https://ollama.com/download)

cd /d "%~dp0.."

echo.
echo ============================================================
echo   VEGA AI — Qwen3 Model Installer
echo ============================================================
echo.
echo This will download 3 Qwen3 models (~43GB total, one-time):
echo.
echo   [1] qwen3:32b       — Max quality (20GB)
echo   [2] qwen3:30b-a3b   — Balanced MoE, fastest smart (18GB)
echo   [3] qwen3:8b        — Fast chat (5GB)
echo.
echo Storage required: ~43GB free disk space
echo.

REM Check Ollama is installed
where ollama >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Ollama not found on PATH.
    echo Please install from: https://ollama.com/download
    pause
    exit /b 1
)

REM Check Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama not running. Starting it now...
    start "" ollama serve
    timeout /t 5 /nobreak >nul
)

echo.
echo ------------------------------------------------------------
echo Pulling qwen3:32b ... (max quality, 20GB)
echo ------------------------------------------------------------
ollama pull qwen3:32b
if errorlevel 1 echo [WARN] qwen3:32b pull failed — may not exist under that exact tag

echo.
echo ------------------------------------------------------------
echo Pulling qwen3:30b-a3b ... (balanced MoE, 18GB)
echo ------------------------------------------------------------
ollama pull qwen3:30b-a3b
if errorlevel 1 echo [WARN] qwen3:30b-a3b pull failed

echo.
echo ------------------------------------------------------------
echo Pulling qwen3:8b ... (fast, 5GB)
echo ------------------------------------------------------------
ollama pull qwen3:8b
if errorlevel 1 echo [WARN] qwen3:8b pull failed

echo.
echo ------------------------------------------------------------
echo Keeping llama3:latest as fallback ...
echo ------------------------------------------------------------
ollama pull llama3:latest

echo.
echo ============================================================
echo   All Qwen3 models installed!
echo ============================================================
echo.
ollama list
echo.
echo You can now start VEGA with: start.bat
echo.
pause
