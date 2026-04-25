"""
VEGA AI — Health & Wellness Agent
Activity reminders, break timers, posture checks, wellness tracking.
"""

import time
from agents import BaseAgent, AgentResult
from core.event_bus import event_bus, Event

HEALTH_SYSTEM = """You are VEGA's Health & Wellness Agent. You help the user maintain healthy habits:
- Remind them to take breaks (20-20-20 rule for eyes, stretch breaks)
- Track water intake, exercise, and sleep patterns
- Provide posture check reminders
- Suggest quick exercises and stretches
- Track daily wellness metrics

Be encouraging and non-judgmental. Focus on building sustainable habits."""


class HealthAgent(BaseAgent):
    name = "health"
    description = "Activity reminders, break timers, posture checks, and wellness tracking"
    capabilities = ["health", "wellness", "breaks", "exercise", "posture", "hydration"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Load wellness data
        wellness = self.memory.procedural.get_preference("wellness_log", {})
        wellness_ctx = ""
        if wellness:
            last_break = wellness.get("last_break", 0)
            minutes_ago = int((time.time() - last_break) / 60) if last_break else "unknown"
            wellness_ctx = f"\n\nLast break: {minutes_ago} minutes ago. Water today: {wellness.get('water_count', 0)} glasses."

        response = await self.router.query(
            prompt=task + wellness_ctx,
            system=HEALTH_SYSTEM,
            task_type="fast",
            temperature=0.6,
            max_tokens=1500
        )

        # Schedule break reminder if needed
        if "break" in task.lower() or "remind" in task.lower():
            await event_bus.publish(Event(
                type="health.reminder_set",
                data={"type": "break", "interval_minutes": 30},
                source=self.name
            ))

        return AgentResult(success=response.success, output=response.text)
