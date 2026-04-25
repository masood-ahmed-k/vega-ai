"""
VEGA AI — Planner Agent (Master)
Uses a ReAct loop (Reason  ->  Act  ->  Observe  ->  Repeat) to decompose tasks,
dispatch to specialized agents, and self-correct on failures.
"""

import json
from agents import BaseAgent, AgentResult, AgentRegistry
import structlog

logger = structlog.get_logger("vega.planner")

PLANNER_SYSTEM = """You are VEGA's Master Planner. You break complex tasks into subtasks and decide which agent handles each.

Available agents: {agents}

For each user request, respond with a JSON plan:
{{
  "thinking": "your reasoning about how to approach this",
  "steps": [
    {{"agent": "agent_name", "task": "specific subtask description", "depends_on": null}},
    {{"agent": "agent_name", "task": "specific subtask description", "depends_on": 0}}
  ],
  "direct_response": null
}}

If the task is simple enough to answer directly without agents, set "direct_response" to your answer and leave "steps" empty.

Rules:
- Break complex tasks into 2-6 subtasks max
- Choose the most appropriate agent for each subtask
- If a subtask depends on another's output, set depends_on to the step index
- If no agent fits, use "planner" to handle it yourself
- Always think step by step
"""


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Master planner that decomposes tasks and orchestrates agents"
    capabilities = ["planning", "orchestration", "reasoning", "conversation"]

    def __init__(self, router, memory, config=None, registry: AgentRegistry = None):
        super().__init__(router, memory, config)
        self.registry = registry
        self.max_iterations = (config or {}).get("max_iterations", 10)

    async def run(self, task: str, context: dict) -> AgentResult:
        # Build agent list for the planner prompt
        agents_desc = ""
        if self.registry:
            for a in self.registry.list_agents():
                agents_desc += f"- {a['name']}: {a.get('description', '')}\n"

        system = PLANNER_SYSTEM.format(agents=agents_desc)

        # Add memory context
        memories = self.memory.recall(task, n=3)
        memory_context = ""
        if memories["episodic"]:
            memory_context = "\n\nRelevant past context:\n" + "\n".join(
                [m["content"] for m in memories["episodic"][:3]]
            )

        # Step 1: Generate plan
        plan_response = await self.router.query(
            prompt=task + memory_context,
            system=system,
            task_type="reasoning",
            temperature=0.3
        )

        # Try to parse JSON plan
        try:
            plan = self._parse_plan(plan_response.text)
        except Exception:
            # If parsing fails, treat as direct response
            return AgentResult(success=True, output=plan_response.text)

        # Direct response — no agents needed
        if plan.get("direct_response"):
            return AgentResult(success=True, output=plan["direct_response"])

        # Step 2: Execute plan with ReAct loop
        steps = plan.get("steps", [])
        if not steps:
            return AgentResult(success=True, output=plan_response.text)

        results = {}
        all_output = []

        for i, step in enumerate(steps):
            agent_name = step.get("agent", "planner")
            subtask = step.get("task", "")
            depends_on = step.get("depends_on")

            # Inject dependency results
            if depends_on is not None and depends_on in results:
                subtask += f"\n\nContext from previous step: {results[depends_on].output[:500]}"

            logger.info("executing_step", step=i, agent=agent_name, task=subtask[:80])

            if agent_name == "planner" or not self.registry:
                # Handle directly
                resp = await self.router.query(prompt=subtask, task_type="reasoning")
                result = AgentResult(success=True, output=resp.text, agent="planner")
            else:
                agent = self.registry.get(agent_name)
                if agent:
                    result = await agent.execute(subtask, context)
                else:
                    # Agent not found — handle with AI
                    resp = await self.router.query(prompt=subtask, task_type="reasoning")
                    result = AgentResult(success=True, output=resp.text, agent="planner")

            results[i] = result
            all_output.append(f"[{agent_name}] {result.output}")

            # ReAct: If step failed, try to self-correct
            if not result.success and self.max_iterations > 0:
                logger.warning("step_failed_retrying", step=i, error=result.error)
                correction = await self.router.query(
                    prompt=f"The previous step failed: {result.error}\nOriginal task: {subtask}\nHow should I retry or work around this?",
                    task_type="reasoning"
                )
                all_output.append(f"[planner:correction] {correction.text}")

        # Step 3: Synthesize final response
        synthesis_prompt = f"""Original request: {task}

Results from subtasks:
{chr(10).join(all_output)}

Synthesize a clear, complete response for the user."""

        final = await self.router.query(prompt=synthesis_prompt, task_type="reasoning", temperature=0.4)

        return AgentResult(
            success=True,
            output=final.text,
            subtasks_completed=len(steps),
            data={"plan": plan, "step_results": {k: v.output[:200] for k, v in results.items()}}
        )

    def _parse_plan(self, text: str) -> dict:
        # Try to extract JSON from the response
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError("No JSON found in planner response")
