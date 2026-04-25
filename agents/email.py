"""
VEGA AI — Email & Calendar Agent
Drafts emails, manages communications, and handles scheduling.
"""

from agents import BaseAgent, AgentResult

EMAIL_SYSTEM = """You are VEGA's Email & Calendar Agent. You help draft professional emails,
manage scheduling, create meeting agendas, and handle communications.

For emails:
- Draft clear, professional messages appropriate to the context
- Include subject line suggestions
- Adapt tone (formal, casual, urgent) based on the situation

For scheduling:
- Suggest optimal meeting times
- Create agendas with time allocations
- Send calendar-style summaries

Always ask for confirmation before sending anything."""


class EmailAgent(BaseAgent):
    name = "email"
    description = "Drafts emails, manages communications, and handles scheduling"
    capabilities = ["email", "calendar", "scheduling", "meeting", "communication"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Pull communication preferences from memory
        prefs = self.memory.procedural.get_preference("email_preferences", {})
        pref_ctx = ""
        if prefs:
            pref_ctx = f"\n\nUser preferences: signature='{prefs.get('signature', '')}', tone='{prefs.get('tone', 'professional')}'"

        response = await self.router.query(
            prompt=task + pref_ctx,
            system=EMAIL_SYSTEM,
            task_type="creative",
            temperature=0.5,
            max_tokens=2000
        )

        return AgentResult(success=response.success, output=response.text)
