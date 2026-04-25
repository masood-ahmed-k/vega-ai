"""
VEGA AI — Browser Agent
Autonomous web browsing with Playwright. Fully local — no paid APIs.

Capabilities: navigate, click, fill forms, extract text/links, screenshot,
          read pages, search Google/Bing, scroll, go back/forward.

VEGA uses Qwen3 to decide WHAT to do; Playwright does it.
"""

import asyncio
import json
from pathlib import Path
import structlog

from agents import BaseAgent, AgentResult

logger = structlog.get_logger("vega.browser")


class BrowserAgent(BaseAgent):
    name = "browser"
    description = "Autonomously browses the web, fills forms, scrapes pages, takes screenshots"
    capabilities = ["web_browse", "web_search", "form_fill", "screenshot",
                    "page_extract", "click", "navigate"]

    def __init__(self, router, memory, config: dict | None = None):
        super().__init__(router, memory, config)
        browser_cfg = (config or {}).get("browser", config or {})
        self.headless = browser_cfg.get("headless", False)
        self.user_data_dir = browser_cfg.get("user_data_dir", "./data/browser_profile")
        self.default_timeout = browser_cfg.get("default_timeout", 30000)
        self.screenshot_dir = Path("./data/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._browser = None
        self._page = None
        self._playwright = None

    async def _ensure_browser(self):
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Browser agent needs Playwright. Install: pip install playwright && playwright install chromium"
            )
        self._playwright = await async_playwright().start()
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
        )
        self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
        self._page.set_default_timeout(self.default_timeout)

    async def run(self, task: str, context: dict) -> AgentResult:
        """Plan and execute a web task via Qwen3 + Playwright."""
        await self._ensure_browser()

        plan_prompt = f"""You are VEGA's browser agent. Given the task, output a JSON plan of steps.
Allowed actions: goto(url), search(query), click(text), fill(selector, value), extract(), screenshot(), scroll(direction).
Return ONLY valid JSON: {{"steps":[{{"action":"...","args":{{...}}}}], "goal":"..."}}

Task: {task}"""
        plan_raw = ""
        try:
            resp = await self.router.query(plan_prompt, task_type="reasoning",
                                           temperature=0.2, max_tokens=1500)
            plan_raw = getattr(resp, "text", "") or ""
        except Exception as e:
            logger.warning("browser_plan_failed", error=str(e))

        plan = self._parse_plan(plan_raw, task)
        results = []
        for step in plan.get("steps", []):
            try:
                out = await self._execute_step(step)
                results.append({"step": step, "result": out[:300] if isinstance(out, str) else out})
            except Exception as e:
                results.append({"step": step, "error": str(e)})

        summary = f"Browser task done. Steps: {len(results)}. Final URL: {self._page.url}"
        self.memory.remember(f"Browser: {task} -> {summary}", role="system",
                             store_long_term=True, metadata={"agent": "browser"})
        return AgentResult(success=True, output=summary,
                           data={"plan": plan, "results": results, "final_url": self._page.url})

    def _parse_plan(self, raw: str, task: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end + 1])
        except Exception as e:
            logger.debug("plan_parse_failed_using_fallback", error=str(e))
        # Fallback — treat task as a search query
        return {"steps": [{"action": "search", "args": {"query": task}},
                          {"action": "extract", "args": {}}],
                "goal": task}

    async def _execute_step(self, step: dict):
        action = step.get("action", "").lower()
        args = step.get("args", {})
        if action == "goto":
            await self._page.goto(args.get("url", ""), wait_until="domcontentloaded")
            return f"navigated to {self._page.url}"
        elif action == "search":
            q = args.get("query", "")
            await self._page.goto(f"https://www.google.com/search?q={q}", wait_until="domcontentloaded")
            return f"searched: {q}"
        elif action == "click":
            text = args.get("text", "")
            await self._page.get_by_text(text, exact=False).first.click()
            return f"clicked: {text}"
        elif action == "fill":
            await self._page.fill(args.get("selector", ""), args.get("value", ""))
            return "filled"
        elif action == "scroll":
            direction = args.get("direction", "down")
            dy = 800 if direction == "down" else -800
            await self._page.evaluate(f"window.scrollBy(0, {dy})")
            return f"scrolled {direction}"
        elif action == "screenshot":
            path = self.screenshot_dir / f"browser_{int(asyncio.get_event_loop().time())}.png"
            await self._page.screenshot(path=str(path), full_page=args.get("full_page", False))
            return str(path)
        elif action == "extract":
            text = await self._page.inner_text("body")
            return text[:4000]
        elif action == "back":
            await self._page.go_back()
            return "back"
        elif action == "forward":
            await self._page.go_forward()
            return "forward"
        else:
            return f"unknown action: {action}"

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning("browser_close_failed", error=str(e))
        self._browser = None
        self._page = None
        self._playwright = None
