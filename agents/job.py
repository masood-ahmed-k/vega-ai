"""
VEGA AI — Job Agent
Finds job opportunities, tracks applications, and provides job market insights.
"""

from agents import BaseAgent, AgentResult

JOB_SYSTEM = """You are VEGA's Job Search Agent. You help find job opportunities, track applications,
analyze job descriptions, match skills to requirements, and provide career strategy advice.
Be specific with job titles, companies, and actionable next steps."""


class JobAgent(BaseAgent):
    name = "job"
    description = "Finds job opportunities, tracks applications, and provides career advice"
    capabilities = ["job_search", "job_tracking", "career_advice", "skill_matching"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Get application history from memory
        history = self.memory.procedural.get_preference("job_applications", [])
        history_ctx = ""
        if history:
            history_ctx = f"\n\nApplication history: {len(history)} applications tracked."

        response = await self.router.query(
            prompt=task + history_ctx,
            system=JOB_SYSTEM,
            task_type="research",
            temperature=0.4,
            max_tokens=3000
        )

        return AgentResult(success=response.success, output=response.text)
