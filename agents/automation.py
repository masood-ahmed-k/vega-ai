"""
VEGA AI — Automation Agent
Controls the computer: mouse, keyboard, applications, and workflow automation.
"""

import asyncio
import subprocess
import json
from pathlib import Path
from agents import BaseAgent, AgentResult
from core.event_bus import event_bus, Event
import structlog

logger = structlog.get_logger("vega.automation")

AUTOMATION_SYSTEM = """You are VEGA's Automation Agent. You control the user's Windows computer.
When given a task, output a JSON list of actions to perform:
[
  {{"action": "open_app", "target": "notepad"}},
  {{"action": "type_text", "text": "Hello World"}},
  {{"action": "hotkey", "keys": ["ctrl", "s"]}},
  {{"action": "click", "x": 500, "y": 300}},
  {{"action": "screenshot"}},
  {{"action": "wait", "seconds": 2}},
  {{"action": "run_command", "command": "dir"}}
]

Available actions: open_app, type_text, hotkey, click, double_click, right_click,
move_mouse, screenshot, wait, run_command, scroll, find_window, focus_window.

Always be precise with coordinates and careful with destructive actions."""


class AutomationAgent(BaseAgent):
    name = "automation"
    description = "Controls mouse, keyboard, applications, and automates workflows"
    capabilities = ["mouse", "keyboard", "app_control", "workflow", "screenshot"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Generate action plan
        response = await self.router.query(
            prompt=f"Task to automate: {task}\n\nGenerate the action sequence.",
            system=AUTOMATION_SYSTEM,
            task_type="reasoning",
            temperature=0.2
        )

        # Parse and execute actions
        try:
            actions = self._parse_actions(response.text)
        except Exception:
            return AgentResult(success=True, output=response.text, data={"note": "Plan generated but not executed (parsing failed)"})

        results = []
        for action in actions:
            result = await self._execute_action(action)
            results.append(result)

        output = f"Executed {len(actions)} automation actions.\n" + "\n".join(results)
        return AgentResult(success=True, output=output, data={"actions": actions})

    async def _execute_action(self, action: dict) -> str:
        act = action.get("action", "")
        try:
            if act == "open_app":
                target = action.get("target", "")
                await asyncio.to_thread(self._open_app, target)
                return f"[OK] Opened {target}"

            elif act == "type_text":
                import pyautogui
                text = action.get("text", "")
                await asyncio.to_thread(pyautogui.write, text, interval=0.03)
                return f"[OK] Typed text ({len(text)} chars)"

            elif act == "hotkey":
                import pyautogui
                keys = action.get("keys", [])
                await asyncio.to_thread(pyautogui.hotkey, *keys)
                return f"[OK] Pressed {'+'.join(keys)}"

            elif act == "click":
                import pyautogui
                x, y = action.get("x", 0), action.get("y", 0)
                await asyncio.to_thread(pyautogui.click, x, y)
                return f"[OK] Clicked ({x}, {y})"

            elif act == "screenshot":
                return await self._take_screenshot()

            elif act == "wait":
                seconds = action.get("seconds", 1)
                await asyncio.sleep(seconds)
                return f"[OK] Waited {seconds}s"

            elif act == "run_command":
                cmd = action.get("command", "")
                result = await asyncio.to_thread(
                    subprocess.run, cmd, shell=True, capture_output=True, text=True, timeout=30
                )
                return f"[OK] Command output: {result.stdout[:200]}"

            elif act == "scroll":
                import pyautogui
                amount = action.get("amount", -3)
                await asyncio.to_thread(pyautogui.scroll, amount)
                return f"[OK] Scrolled {amount}"

            else:
                return f"[!] Unknown action: {act}"

        except Exception as e:
            return f"[FAIL] {act} failed: {str(e)}"

    def _open_app(self, target: str):
        import subprocess
        # Try common Windows app paths
        app_map = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "browser": "start chrome",
            "chrome": "start chrome",
            "explorer": "explorer.exe",
            "terminal": "wt.exe",
            "cmd": "cmd.exe",
            "vscode": "code",
        }
        cmd = app_map.get(target.lower(), target)
        subprocess.Popen(cmd, shell=True)

    async def _take_screenshot(self) -> str:
        try:
            import mss
            import mss.tools
            screenshot_dir = Path(self.config.get("screenshot_dir", "./data/screenshots"))
            screenshot_dir.mkdir(parents=True, exist_ok=True)

            with mss.mss() as sct:
                import time
                filename = screenshot_dir / f"screenshot_{int(time.time())}.png"
                sct.shot(output=str(filename))

            await event_bus.publish(Event(type="screenshot.taken", data={"path": str(filename)}, source=self.name))
            return f"[OK] Screenshot saved: {filename}"
        except Exception as e:
            return f"[FAIL] Screenshot failed: {e}"

    def _parse_actions(self, text: str) -> list[dict]:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError("No action JSON found")
