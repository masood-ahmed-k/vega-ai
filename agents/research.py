"""
VEGA AI — Research Agent
Gathers information from the internet, summarizes findings, and provides sourced answers.
"""

import asyncio
import httpx
from agents import BaseAgent, AgentResult
import structlog

logger = structlog.get_logger("vega.research")

RESEARCH_SYSTEM = """You are VEGA's Research Agent. You analyze information and provide well-structured, sourced answers.
When given search results, synthesize them into a clear, comprehensive response.
Always cite your reasoning and note when information may be outdated or uncertain."""


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Searches the internet and synthesizes information"
    capabilities = ["search", "research", "summarize", "fact_check"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Use the AI model to process the research task
        # In production, integrate with web search APIs (SerpAPI, Tavily, etc.)

        search_prompt = f"""Research task: {task}

Please provide a comprehensive answer. If you need to search the web, describe what you would search for and provide the best answer from your knowledge.

Structure your response with:
1. Key findings
2. Details and analysis
3. Sources or confidence level"""

        response = await self.router.query(
            prompt=search_prompt,
            system=RESEARCH_SYSTEM,
            task_type="research",
            temperature=0.3,
            max_tokens=3000
        )

        return AgentResult(success=response.success, output=response.text)
