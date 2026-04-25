@echo off
REM VEGA AI — Voice (free, local) Dependencies

cd /d "%~dp0.."

echo.
echo ============================================================
echo   VEGA AI — Voice Dependencies (FREE, local)
echo ============================================================
echo.
echo Installs: whisper (STT), pyttsx3 (TTS), speech_recognition.
echo Call mode: hands-free conversation (no wake word).
echo.
pause

python -m pip install SpeechRecognition openai-whisper pyttsx3

REM pyaudio can fail on Windows — use pipwin fallback
python -m pip install pyaudio
if errorlevel 1 (
    echo pyaudio direct install failed, trying pipwin...
    python -m pip install pipwin
    python -m pipwin install pyaudio
)

echo.
echo [OK] Voice ready. Enable in config/settings.yaml:  voice.enabled: true
echo.
pause
