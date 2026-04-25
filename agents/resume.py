"""
VEGA AI — Resume Agent
Generates, edits, and optimizes resumes and cover letters.
"""

from agents import BaseAgent, AgentResult

RESUME_SYSTEM = """You are VEGA's Resume Agent. You create professional, ATS-optimized resumes and cover letters.
You understand modern resume formats, keyword optimization, and industry-specific requirements.
Always output in a clean, structured format ready for document generation."""


class ResumeAgent(BaseAgent):
    name = "resume"
    description = "Creates, edits, and optimizes resumes and cover letters"
    capabilities = ["resume", "cover_letter", "cv", "career"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Check memory for user profile
        profile = self.memory.procedural.get_preference("user_profile", {})
        profile_context = ""
        if profile:
            profile_context = f"\n\nUser profile: {profile}"

        response = await self.router.query(
            prompt=task + profile_context,
            system=RESUME_SYSTEM,
            task_type="creative",
            temperature=0.5,
            max_tokens=4000
        )

        return AgentResult(success=response.success, output=response.text)
