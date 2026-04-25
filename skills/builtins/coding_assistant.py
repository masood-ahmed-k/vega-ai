"""
VEGA AI — Coding Assistant Skill
Advanced code generation, review, debugging, and architecture advice.
"""

from agents import BaseAgent, AgentResult

CODING_SYSTEM = """You are an expert coding assistant. You excel at:
- Writing clean, production-grade code in any language
- Debugging with systematic root-cause analysis
- Code review with security and performance insights
- Architecture design and system design
- Refactoring legacy code
- Writing tests and documentation

Always include error handling. Prefer modern idioms and best practices.
Explain your design decisions when relevant."""


class CodingAssistantSkill(BaseAgent):
    name = "coding_assistant_skill"
    description = "Advanced code generation, review, debugging, and architecture advice"
    capabilities = ["code_generation", "debugging", "code_review", "architecture", "refactoring"]

    async def run(self, task: str, context: dict) -> AgentResult:
        response = await self.router.query(
            prompt=task,
            system=CODING_SYSTEM,
            task_type="coding",
            temperature=0.3,
            max_tokens=4000
        )
        return AgentResult(success=response.success, output=response.text)
