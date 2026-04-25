"""
VEGA AI — Study Agent
Creates learning plans, study schedules, quizzes, and tracks progress.
"""

from agents import BaseAgent, AgentResult

STUDY_SYSTEM = """You are VEGA's Study Agent. You create personalized learning plans, study schedules,
explain complex topics, generate practice quizzes, and track learning progress.
Structure your learning plans with clear milestones, resources, and timelines.
Adapt to the user's learning pace and style."""


class StudyAgent(BaseAgent):
    name = "study"
    description = "Creates learning plans, study schedules, and tracks educational progress"
    capabilities = ["study_plan", "learning", "quiz", "explain", "education"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Retrieve study progress from memory
        progress = self.memory.procedural.get_preference("study_progress", {})
        progress_ctx = ""
        if progress:
            topics = list(progress.keys())
            progress_ctx = f"\n\nCurrent study progress: {', '.join(topics)}"

        response = await self.router.query(
            prompt=task + progress_ctx,
            system=STUDY_SYSTEM,
            task_type="reasoning",
            temperature=0.5,
            max_tokens=4000
        )

        return AgentResult(success=response.success, output=response.text)
