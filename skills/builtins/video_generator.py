"""
VEGA AI — Video Generator Skill
Hot-loadable wrapper around VideoAgent so the Planner can call it via natural language.

Example: "VEGA, make a video of a futuristic city"  ->  routes here  ->  VideoAgent.
"""

from agents import BaseAgent, AgentResult
from agents.video import VideoAgent


class VideoGeneratorSkill(BaseAgent):
    name = "video_generator"
    description = "Generates Full HD animated videos from text prompts (8 FREE providers)"
    capabilities = ["text_to_video", "animation", "video_creation"]

    def __init__(self, router, memory, config=None):
        super().__init__(router, memory, config)
        self._video_agent = VideoAgent(router, memory, config)

    async def run(self, task: str, context: dict) -> AgentResult:
        provider = context.get("provider")
        resolution = context.get("resolution", "1920x1080")
        duration = context.get("duration", 5)

        # Sniff provider from prompt (FREE providers only — no runway/replicate)
        task_lower = task.lower()
        if not provider:
            for p in ["wan2", "cogvideox", "ltx", "animatediff",
                      "huggingface", "zsky", "json2video", "luma"]:
                if p in task_lower:
                    provider = p
                    break

        ctx = dict(context)
        if provider:
            ctx["provider"] = provider
        ctx["resolution"] = resolution
        ctx["duration"] = duration
        ctx.setdefault("async_mode", True)  # Return job_id immediately; HUD polls progress

        return await self._video_agent.execute(task, ctx)

    def get_agent(self) -> VideoAgent:
        """Direct access to the underlying VideoAgent (used by API layer)."""
        return self._video_agent
