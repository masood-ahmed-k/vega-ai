"""
VEGA AI — Code Agent
Writes, runs, debugs, and explains code in a sandboxed environment.
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from agents import BaseAgent, AgentResult
import structlog

logger = structlog.get_logger("vega.code")

CODE_SYSTEM = """You are VEGA's Code Agent. You write, debug, and explain code.

When asked to write code:
1. Write clean, well-commented, production-quality code
2. Include error handling
3. If the user wants to run it, wrap the code in ```python or ```javascript blocks

When asked to debug:
1. Identify the bug
2. Explain why it happens
3. Provide the fix

When asked to explain:
1. Break down the logic step by step
2. Use analogies when helpful

Always specify the language and any dependencies needed."""


class CodeAgent(BaseAgent):
    name = "code"
    description = "Writes, runs, debugs, and explains code"
    capabilities = ["coding", "debugging", "code_review", "scripting", "programming"]

    async def run(self, task: str, context: dict) -> AgentResult:
        response = await self.router.query(
            prompt=task,
            system=CODE_SYSTEM,
            task_type="coding",
            temperature=0.3,
            max_tokens=4000
        )

        # Check if user wants to execute the code
        if context.get("execute", False) or "run" in task.lower():
            code_blocks = self._extract_code(response.text)
            if code_blocks:
                exec_results = []
                for lang, code in code_blocks:
                    if lang in ("python", "py"):
                        result = await self._run_python(code)
                        exec_results.append(f"--- Execution Result ---\n{result}")
                output = response.text + "\n\n" + "\n".join(exec_results)
                return AgentResult(success=True, output=output)

        return AgentResult(success=response.success, output=response.text)

    async def _run_python(self, code: str) -> str:
        """Run Python code in a subprocess sandbox."""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()) as f:
                f.write(code)
                f.flush()
                timeout = self.config.get("timeout", 30)
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["python", f.name],
                    capture_output=True, text=True, timeout=timeout
                )
                output = result.stdout
                if result.stderr:
                    output += f"\nSTDERR: {result.stderr}"
                return output[:2000]
        except subprocess.TimeoutExpired:
            return "[!] Execution timed out"
        except Exception as e:
            return f"[!] Execution error: {str(e)}"

    def _extract_code(self, text: str) -> list[tuple[str, str]]:
        blocks = []
        parts = text.split("```")
        for i in range(1, len(parts), 2):
            block = parts[i]
            lines = block.strip().split("\n")
            lang = lines[0].strip().lower() if lines else ""
            code = "\n".join(lines[1:]) if lang else block
            if not lang:
                lang = "python"
            blocks.append((lang, code))
        return blocks
