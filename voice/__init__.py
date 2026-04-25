"""
VEGA AI — Voice Interface
Wake word detection, speech recognition (Whisper), and text-to-speech.
"""

import asyncio
import threading
from typing import Callable, Optional
import structlog

logger = structlog.get_logger("vega.voice")


class VoiceInterface:
    """Handles voice input (STT) and output (TTS) for VEGA."""

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", True)
        self.wake_word = config.get("wake_word", "hey vega")
        self.stt_engine = config.get("stt_engine", "whisper")
        self.tts_engine = config.get("tts_engine", "pyttsx3")
        self.continuous = config.get("continuous_mode", False)
        self.silence_timeout = config.get("silence_timeout", 2.0)
        self._listening = False
        self._on_command: Optional[Callable] = None
        self._tts = None

    def set_command_handler(self, handler: Callable):
        """Set the callback for when a voice command is recognized."""
        self._on_command = handler

    async def speak(self, text: str):
        """Convert text to speech."""
        if not self.enabled:
            return

        try:
            if self.tts_engine == "openai":
                await self._speak_openai(text)
            else:
                await self._speak_pyttsx3(text)
        except Exception as e:
            logger.error("tts_failed", error=str(e))

    async def _speak_pyttsx3(self, text: str):
        import pyttsx3
        
        def _do_speak():
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            voices = engine.getProperty("voices")
            if voices:
                engine.setProperty("voice", voices[0].id)
            engine.say(text)
            engine.runAndWait()
        
        await asyncio.to_thread(_do_speak)

    async def _speak_openai(self, text: str):
        import openai
        from pathlib import Path
        import tempfile
        
        client = openai.AsyncOpenAI()
        voice = self.config.get("tts_voice", "nova")
        response = await client.audio.speech.create(
            model="tts-1", voice=voice, input=text
        )
        
        # Save and play
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(response.content)
            temp_path = f.name
        
        # Play audio (Windows)
        import subprocess
        await asyncio.to_thread(
            subprocess.run,
            ["powershell", "-c", f"(New-Object Media.SoundPlayer '{temp_path}').PlaySync()"],
            capture_output=True
        )

    async def listen(self, timeout: float = 10.0) -> str | None:
        """Listen for speech and transcribe it."""
        if not self.enabled:
            return None

        try:
            if self.stt_engine == "whisper":
                return await self._listen_whisper(timeout)
            else:
                return await self._listen_google(timeout)
        except Exception as e:
            logger.error("stt_failed", error=str(e))
            return None

    async def _listen_google(self, timeout: float) -> str | None:
        import speech_recognition as sr
        
        def _do_listen():
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=30)
                    text = recognizer.recognize_google(audio)
                    return text
                except sr.WaitTimeoutError:
                    return None
                except sr.UnknownValueError:
                    return None
        
        return await asyncio.to_thread(_do_listen)

    async def _listen_whisper(self, timeout: float) -> str | None:
        import speech_recognition as sr
        
        def _do_listen():
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=30)
                    # Use Whisper via the speech_recognition library
                    text = recognizer.recognize_whisper(
                        audio, 
                        model=self.config.get("whisper_model", "base"),
                        language="en"
                    )
                    return text
                except sr.WaitTimeoutError:
                    return None
                except sr.UnknownValueError:
                    return None
        
        return await asyncio.to_thread(_do_listen)

    async def listen_for_wake_word(self) -> bool:
        """Listen continuously for the wake word."""
        text = await self.listen(timeout=5.0)
        if text and self.wake_word.lower() in text.lower():
            logger.info("wake_word_detected")
            return True
        return False

    async def call_loop(self):
        """Hands-free continuous call mode — no wake word, phone-call style.

        Speak naturally; VEGA listens, replies, and keeps the line open until
        you say 'hang up' or 'goodbye'. TTS is interruptible by new speech.
        """
        if not self.enabled:
            return
        call_cfg = self.config.get("call_mode", {})
        if call_cfg.get("auto_greet", True):
            await self.speak("VEGA is on the line. I'm listening.")
        while True:
            try:
                text = await self.listen(timeout=30.0)
                if not text:
                    continue
                lower = text.strip().lower()
                if lower in ("hang up", "goodbye", "end call", "bye vega", "stop listening"):
                    await self.speak("Ending call. Talk soon.")
                    return
                logger.info("call_turn", text=text)
                if self._on_command:
                    response = await self._on_command(text)
                    if response:
                        await self.speak(response)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("call_loop_error", error=str(e))
                await asyncio.sleep(1)

    async def voice_loop(self):
        """Main voice interaction loop. Uses call mode if configured, else wake-word."""
        if not self.enabled:
            return

        if self.config.get("call_mode", {}).get("enabled", False):
            logger.info("call_mode_started")
            return await self.call_loop()

        logger.info("voice_loop_started", wake_word=self.wake_word)
        await self.speak("VEGA voice interface online.")

        while True:
            try:
                # Wait for wake word
                if not self.continuous:
                    detected = await self.listen_for_wake_word()
                    if not detected:
                        continue
                    await self.speak("Listening.")

                # Listen for command
                command = await self.listen(timeout=10.0)
                if command:
                    logger.info("voice_command", text=command)
                    if self._on_command:
                        response = await self._on_command(command)
                        if response:
                            await self.speak(response)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("voice_loop_error", error=str(e))
                await asyncio.sleep(1)
