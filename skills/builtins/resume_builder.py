"""
VEGA AI — Resume Builder Skill
Generates ATS-optimized resumes and cover letters tailored to specific job postings.
"""

from agents import BaseAgent, AgentResult

RESUME_BUILDER_SYSTEM = """You are an expert resume and cover letter writer. You create:
- ATS-optimized resumes that pass automated screening
- Tailored cover letters matched to specific job postings
- LinkedIn profile summaries
- Professional bio statements

Best practices:
- Use strong action verbs and quantified achievements
- Match keywords from job descriptions
- Clean, scannable formatting
- Customize for each role
- Include relevant technical skills prominently

Output in clean, structured text format ready for document generation."""


class ResumeBuilderSkill(BaseAgent):
    name = "resume_builder_skill"
    description = "Creates ATS-optimized resumes and cover letters"
    capabilities = ["resume_generation", "cover_letter", "linkedin_profile", "professional_bio"]

    async def run(self, task: str, context: dict) -> AgentResult:
        profile = self.memory.procedural.get_preference("user_profile", {})
        ctx = ""
        if profile:
            ctx = f"\n\nUser profile data: {profile}"

        response = await self.router.query(
            prompt=task + ctx,
            system=RESUME_BUILDER_SYSTEM,
            task_type="creative",
            temperature=0.5,
            max_tokens=4000
        )
        return AgentResult(success=response.success, output=response.text)
