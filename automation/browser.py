"""
VEGA AI — Browser Automation
Controls web browsers using Playwright for web automation tasks.
"""

import asyncio
from typing import Optional
import structlog

logger = structlog.get_logger("vega.browser")


class BrowserAutomation:
    """Web browser automation using Playwright."""

    def __init__(self, config: dict):
        self.config = config
        self.headless = config.get("headless", False)
        self.timeout = config.get("default_timeout", 30000)
        self._browser = None
        self._context = None
        self._page = None

    async def launch(self):
        try:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            self._page.set_default_timeout(self.timeout)
            logger.info("browser_launched")
        except Exception as e:
            logger.error("browser_launch_failed", error=str(e))
            raise

    async def navigate(self, url: str) -> str:
        if not self._page:
            await self.launch()
        await self._page.goto(url, wait_until="domcontentloaded")
        return await self._page.title()

    async def get_text(self) -> str:
        if not self._page:
            return ""
        return await self._page.inner_text("body")

    async def click(self, selector: str):
        if self._page:
            await self._page.click(selector)

    async def fill(self, selector: str, value: str):
        if self._page:
            await self._page.fill(selector, value)

    async def screenshot(self, path: str = None) -> bytes:
        if self._page:
            return await self._page.screenshot(path=path, full_page=True)
        return b""

    async def evaluate(self, script: str) -> any:
        if self._page:
            return await self._page.evaluate(script)
        return None

    async def search_google(self, query: str) -> list[dict]:
        """Perform a Google search and return results."""
        await self.navigate(f"https://www.google.com/search?q={query}")
        await asyncio.sleep(2)
        
        results = await self._page.evaluate("""
            () => {
                const items = document.querySelectorAll('.g');
                return Array.from(items).slice(0, 10).map(item => ({
                    title: item.querySelector('h3')?.textContent || '',
                    url: item.querySelector('a')?.href || '',
                    snippet: item.querySelector('.VwiC3b')?.textContent || ''
                }));
            }
        """)
        return results or []

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, '_pw') and self._pw:
            await self._pw.stop()
            self._pw = None
        logger.info("browser_closed")
