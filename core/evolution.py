"""
VEGA AI — Self-Evolution Engine
Autonomously rewrites agents, generates new skills, optimizes routing,
and refactors its own code. Creates snapshots before every modification.
"""

import time
import json
from pathlib import Path
from typing import Optional
import structlog

from core.event_bus import event_bus, Event

logger = structlog.get_logger("vega.evolution")

EVOLUTION_SYSTEM = """You are VEGA's Self-Evolution Engine. You analyze performance data and generate improved code.

When asked to optimize an agent:
1. Analyze the performance metrics and failure patterns
2. Generate improved Python code for the agent
3. The code must be a complete, valid Python file
4. Include all imports and maintain the same class interface

When asked to generate a new skill:
1. Create a complete skill module
2. Follow the BaseAgent pattern
3. Include docstring, capabilities list, and run() method

Output only valid Python code wrapped in ```python blocks.
Never remove safety features or snapshot capabilities."""


class EvolutionEngine:
    """Self-improvement system that can rewrite VEGA's own code."""

    def __init__(self, config: dict, router, memory, security):
        self.config = config
        self.router = router
        self.memory = memory
        self.security = security
        self.enabled = config.get("enabled", True)
        self.min_confidence = config.get("min_confidence_to_evolve", 0.7)
        self.evolution_log = []

    async def analyze_performance(self) -> dict:
        """Analyze agent performance and identify improvement opportunities."""
        tasks = self.memory.procedural.get_recent_tasks(limit=100)
        
        # Calculate per-agent stats
        agent_stats = {}
        for task in tasks:
            agent = task["agent"]
            if agent not in agent_stats:
                agent_stats[agent] = {"total": 0, "success": 0, "failures": 0, "avg_duration": 0, "total_duration": 0}
            agent_stats[agent]["total"] += 1
            if task["success"]:
                agent_stats[agent]["success"] += 1
            else:
                agent_stats[agent]["failures"] += 1
            agent_stats[agent]["total_duration"] += task["duration"]
            agent_stats[agent]["avg_duration"] = agent_stats[agent]["total_duration"] / agent_stats[agent]["total"]

        # Identify weak agents
        improvements_needed = []
        for agent, stats in agent_stats.items():
            success_rate = stats["success"] / max(1, stats["total"])
            if success_rate < 0.7 and stats["total"] >= 5:
                improvements_needed.append({
                    "agent": agent,
                    "success_rate": success_rate,
                    "total_tasks": stats["total"],
                    "avg_duration": stats["avg_duration"]
                })

        return {
            "agent_stats": agent_stats,
            "improvements_needed": improvements_needed,
            "total_tasks_analyzed": len(tasks),
            "router_stats": self.router.get_stats_summary()
        }

    async def evolve_agent(self, agent_name: str, reason: str = "performance_optimization") -> dict:
        """Rewrite an agent's code to improve it."""
        if not self.enabled:
            return {"success": False, "reason": "Evolution disabled"}

        # Snapshot before modification
        snapshot_id = self.security.snapshots.create_snapshot(
            reason=f"pre_evolution_{agent_name}",
            files=[f"agents/{agent_name}.py"]
        )

        # Read current agent code
        agent_path = Path(f"agents/{agent_name}.py")
        if not agent_path.exists():
            return {"success": False, "reason": f"Agent file not found: {agent_path}"}

        current_code = agent_path.read_text()

        # Get performance data
        perf = await self.analyze_performance()
        agent_perf = perf["agent_stats"].get(agent_name, {})

        # Get failure examples
        recent_tasks = self.memory.procedural.get_recent_tasks(limit=50)
        failures = [t for t in recent_tasks if t["agent"] == agent_name and not t["success"]]

        # Ask AI to generate improved code
        prompt = f"""Analyze and improve this VEGA agent:

Current code:
```python
{current_code}
```

Performance data:
- Success rate: {agent_perf.get('success', 0)}/{agent_perf.get('total', 0)}
- Average duration: {agent_perf.get('avg_duration', 0):.2f}s
- Recent failures: {json.dumps(failures[:5], indent=2, default=str)}

Reason for evolution: {reason}

Generate an improved version of this agent. Keep the same class name and interface.
Focus on: better error handling, smarter prompts, improved task parsing, and reliability."""

        response = await self.router.query(
            prompt=prompt,
            system=EVOLUTION_SYSTEM,
            task_type="coding",
            temperature=0.3,
            max_tokens=4000
        )

        # Extract code from response
        new_code = self._extract_code(response.text)
        if not new_code:
            return {"success": False, "reason": "Failed to generate valid code", "snapshot_id": snapshot_id}

        # Validate the code (basic syntax check)
        try:
            compile(new_code, agent_path, "exec")
        except SyntaxError as e:
            return {"success": False, "reason": f"Generated code has syntax error: {e}", "snapshot_id": snapshot_id}

        # Write the new code
        agent_path.write_text(new_code)

        # Log the evolution
        evolution_entry = {
            "agent": agent_name,
            "reason": reason,
            "snapshot_id": snapshot_id,
            "timestamp": time.time(),
            "success": True
        }
        self.evolution_log.append(evolution_entry)

        await event_bus.publish(Event(
            type="evolution.agent_evolved",
            data=evolution_entry,
            source="evolution_engine"
        ))

        logger.info("agent_evolved", agent=agent_name, snapshot=snapshot_id)
        return {"success": True, "snapshot_id": snapshot_id, "agent": agent_name}

    async def generate_skill(self, name: str, description: str, capabilities: list[str]) -> dict:
        """Auto-generate a new skill/agent."""
        if not self.enabled:
            return {"success": False, "reason": "Evolution disabled"}

        snapshot_id = self.security.snapshots.create_snapshot(reason=f"pre_skill_gen_{name}")

        prompt = f"""Generate a new VEGA skill agent:

Name: {name}
Description: {description}
Capabilities: {', '.join(capabilities)}

Create a complete Python agent file following this pattern:
- Import from agents import BaseAgent, AgentResult
- Define a class that inherits BaseAgent
- Set name, description, capabilities
- Implement async run(self, task, context) method
- Use self.router.query() for AI calls
- Use self.memory for persistent storage

The agent should be practical, well-documented, and handle errors gracefully."""

        response = await self.router.query(
            prompt=prompt,
            system=EVOLUTION_SYSTEM,
            task_type="coding",
            temperature=0.4,
            max_tokens=3000
        )

        code = self._extract_code(response.text)
        if not code:
            return {"success": False, "reason": "Failed to generate skill code"}

        # Auto-generated skills (from detect_repeated_requests) go to skills/generated/
        # Hand-requested ones go to skills/builtins/
        sub_dir = "generated" if name.startswith("auto_") else "builtins"
        skill_path = Path(f"skills/{sub_dir}/{name}.py")
        skill_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            compile(code, str(skill_path), "exec")
        except SyntaxError as e:
            return {"success": False, "reason": f"Syntax error: {e}"}

        skill_path.write_text(code)

        await event_bus.publish(Event(
            type="evolution.skill_generated",
            data={"name": name, "path": str(skill_path)},
            source="evolution_engine"
        ))

        logger.info("skill_generated", name=name, path=str(skill_path))
        return {"success": True, "path": str(skill_path), "snapshot_id": snapshot_id}

    async def optimize_router(self):
        """Analyze model performance and update routing preferences."""
        stats = self.router.get_stats_summary()
        
        for task_type, models in stats.items():
            best_model = max(models.items(), key=lambda x: x[1].get("score", 0), default=(None, None))
            if best_model[0] and best_model[1].get("score", 0) > self.min_confidence:
                logger.info("router_optimized", task=task_type, best_model=best_model[0], score=best_model[1]["score"])

    async def auto_evolve(self):
        """Run full evolution cycle: analyze, optimize, evolve weak agents, detect repeats."""
        if not self.enabled:
            return

        perf = await self.analyze_performance()
        await self.optimize_router()

        for improvement in perf.get("improvements_needed", []):
            agent_name = improvement["agent"]
            if improvement["success_rate"] < 0.5:
                logger.info("auto_evolving_agent", agent=agent_name, success_rate=improvement["success_rate"])
                await self.evolve_agent(agent_name, reason="auto_evolution_low_success_rate")

        # Auto-skill-gen for repeated requests
        await self.detect_repeated_requests()

    async def detect_repeated_requests(self):
        """If the user keeps asking similar things, auto-generate a skill for it."""
        threshold = self.config.get("auto_skill_threshold", 3)
        similarity = self.config.get("auto_skill_similarity", 0.85)
        tasks = self.memory.procedural.get_recent_tasks(limit=100)
        if not tasks:
            return

        # Group by normalized prefix (cheap similarity heuristic)
        buckets: dict[str, list[dict]] = {}
        for t in tasks:
            key = " ".join((t.get("task", "") or "").lower().split()[:4])
            if not key:
                continue
            buckets.setdefault(key, []).append(t)

        # Skip trivial / conversational keys that shouldn't become skills
        trivial = {"hi", "hello", "hey", "yes", "no", "ok", "thanks", "thank", "bye",
                   "test", "ping", "help", "cool", "nice", "good", "bad", "sure"}

        for key, group in buckets.items():
            if len(group) < threshold:
                continue
            first_word = key.split()[0] if key.split() else ""
            if first_word in trivial or len(key) < 10:
                continue
            # Skip if all covered by one real agent already
            agents = {t.get("agent", "") for t in group}
            if len(agents) == 1 and list(agents)[0] not in ("planner", "system", ""):
                continue
            skill_name = "auto_" + "_".join(key.split())[:40]
            existing = Path(f"skills/generated/{skill_name}.py")
            if existing.exists():
                continue
            sample_task = group[0].get("task", key)
            logger.info("auto_generating_skill", key=key, count=len(group))
            await self.generate_skill(
                name=skill_name,
                description=f"Auto-generated skill for repeated requests like '{sample_task}'",
                capabilities=[key]
            )

    def _extract_code(self, text: str) -> str | None:
        if "```python" in text:
            code = text.split("```python")[1].split("```")[0]
            return code.strip()
        elif "```" in text:
            code = text.split("```")[1].split("```")[0]
            return code.strip()
        return None
