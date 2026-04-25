"""
VEGA AI — Study Planner Skill
Creates structured learning plans with milestones and resource recommendations.
"""

from agents import BaseAgent, AgentResult

STUDY_PLANNER_SYSTEM = """You are a specialized study planning assistant. You create detailed, personalized learning plans.

For every study plan, include:
1. Learning objectives with measurable outcomes
2. Weekly schedule with specific topics and time estimates
3. Recommended resources (courses, books, tutorials, projects)
4. Milestones and checkpoints
5. Practice projects or exercises for each phase
6. Estimated total duration to proficiency

Structure the plan in clear phases: Foundation  ->  Intermediate  ->  Advanced  ->  Mastery.
Tailor to the user's existing knowledge level and available time."""


class StudyPlannerSkill(BaseAgent):
    name = "study_planner_skill"
    description = "Creates detailed, structured learning plans with milestones"
    capabilities = ["study_plan", "curriculum", "learning_path", "course_recommendation"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Get user's study history
        progress = self.memory.procedural.get_preference("study_progress", {})
        ctx = ""
        if progress:
            ctx = f"\n\nExisting progress: {progress}"

        response = await self.router.query(
            prompt=task + ctx,
            system=STUDY_PLANNER_SYSTEM,
            task_type="reasoning",
            temperature=0.5,
            max_tokens=4000
        )
        return AgentResult(success=response.success, output=response.text)
