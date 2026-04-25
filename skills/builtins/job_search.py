"""
VEGA AI — Job Search Skill (Builtin)
Enhanced job search with tracking and analysis.
"""

from agents import BaseAgent, AgentResult

JOB_SEARCH_SYSTEM = """You are a specialized job search assistant. You help with:
- Finding job postings matching specific criteria
- Analyzing job descriptions for key requirements
- Suggesting resume keywords based on job postings
- Tracking application status
- Preparing for interviews

Provide actionable, specific advice with concrete examples."""


class JobSearchSkill(BaseAgent):
    name = "job_search_skill"
    description = "Advanced job search, analysis, and application tracking"
    capabilities = ["job_search", "job_analysis", "interview_prep", "application_tracking"]

    async def run(self, task: str, context: dict) -> AgentResult:
        response = await self.router.query(
            prompt=task,
            system=JOB_SEARCH_SYSTEM,
            task_type="research",
            temperature=0.4,
            max_tokens=3000
        )
        return AgentResult(success=response.success, output=response.text)
