"""
VEGA AI — Screen Vision
Captures screenshots, analyzes screen content with AI, and detects UI elements.
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger("vega.vision")


class ScreenVision:
    """Captures and analyzes screen content."""

    def __init__(self, config: dict, router):
        self.config = config
        self.router = router
        self.screenshot_dir = Path(config.get("screenshot_dir", "./data/screenshots"))
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def capture(self, region: dict | None = None) -> Path:
        """Capture a screenshot. Returns file path."""
        try:
            import mss
            with mss.mss() as sct:
                if region:
                    monitor = region
                else:
                    monitor = sct.monitors[1]  # Primary monitor

                screenshot = sct.grab(monitor)
                filename = self.screenshot_dir / f"capture_{int(time.time())}.png"
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filename))
                logger.info("screenshot_captured", path=str(filename))
                return filename
        except Exception as e:
            logger.error("screenshot_failed", error=str(e))
            raise

    async def analyze(self, image_path: Path | str, question: str = "Describe what you see on screen.") -> str:
        """Analyze a screenshot using AI vision."""
        image_path = Path(image_path)
        if not image_path.exists():
            return "Image file not found."

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Try OpenAI vision first
        try:
            import openai
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}", "detail": "high"}}
                    ]
                }],
                max_tokens=1500
            )
            return response.choices[0].message.content or "No analysis generated."
        except Exception as e:
            logger.warning("openai_vision_failed", error=str(e))

        # Fallback to Claude vision
        try:
            import anthropic
            client = anthropic.AsyncAnthropic()
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
                        {"type": "text", "text": question}
                    ]
                }]
            )
            return response.content[0].text if response.content else "No analysis generated."
        except Exception as e:
            logger.error("vision_analysis_failed", error=str(e))
            return f"Vision analysis failed: {str(e)}"

    async def capture_and_analyze(self, question: str = "Describe what you see on screen.") -> dict:
        """Capture screenshot and analyze it in one call."""
        path = await self.capture()
        analysis = await self.analyze(path, question)
        return {"screenshot_path": str(path), "analysis": analysis}

    async def find_element(self, description: str) -> dict | None:
        """Find a UI element by description using vision AI."""
        path = await self.capture()
        prompt = f"""Look at this screenshot and find the UI element matching: "{description}"
        
Return the approximate coordinates as JSON:
{{"found": true, "x": 500, "y": 300, "description": "the button labeled Submit"}}

If not found:
{{"found": false, "description": "Element not found on screen"}}"""

        analysis = await self.analyze(path, prompt)
        try:
            import json
            # Extract JSON from response
            start = analysis.find("{")
            end = analysis.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(analysis[start:end])
        except Exception:
            pass
        return None

    async def monitor_changes(self, interval: float = 5.0, duration: float = 60.0, callback=None):
        """Monitor screen for changes over a period."""
        start_time = time.time()
        prev_path = await self.capture()
        
        while time.time() - start_time < duration:
            await asyncio.sleep(interval)
            new_path = await self.capture()
            
            analysis = await self.analyze(
                new_path,
                "Compare this screenshot to the previous state. What changed? Be specific."
            )
            
            if callback:
                await callback({"path": str(new_path), "changes": analysis})
            
            prev_path = new_path
