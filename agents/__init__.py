"""
VEGA AI — Agent System
Base agent class with lifecycle, and a registry for hot-plugging agents.
"""

import time
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field
import structlog

from core.event_bus import event_bus, Event
from core.logger import audit_log

logger = structlog.get_logger("vega.agents")


@dataclass
class AgentResult:
    success: bool
    output: str
    data: Any = None
    agent: str = ""
    duration: float = 0.0
    subtasks_completed: int = 0
    error: str = ""


class BaseAgent(ABC):
    """Base class for all VEGA agents."""

    name: str = "base"
    description: str = "Base agent"
    capabilities: list[str] = []

    def __init__(self, router, memory, config: dict | None = None):
        self.router = router
        self.memory = memory
        self.config = config or {}
        self.is_active = False
        self.total_tasks = 0
        self.successful_tasks = 0

    async def execute(self, task: str, context: dict | None = None) -> AgentResult:
        """Execute a task with logging, timing, and event publishing."""
        self.is_active = True
        self.total_tasks += 1
        start = time.time()

        await event_bus.publish(Event(type="agent.started", data={"agent": self.name, "task": task}, source=self.name))
        audit_log("task_started", agent=self.name, details=f"task={task[:100]}")

        try:
            result = await self.run(task, context or {})
            result.agent = self.name
            result.duration = time.time() - start

            if result.success:
                self.successful_tasks += 1

            # Store in memory
            self.memory.remember(
                f"Agent {self.name} completed: {task[:200]}  ->  {result.output[:200]}",
                role="system", store_long_term=True,
                metadata={"agent": self.name, "success": result.success}
            )
            self.memory.procedural.record_task(task, self.name, result.output[:500], result.success, result.duration)

            await event_bus.publish(Event(
                type="agent.completed", source=self.name,
                data={"agent": self.name, "task": task, "success": result.success, "duration": result.duration}
            ))
            audit_log("task_completed", agent=self.name, details=f"success={result.success} duration={result.duration:.2f}s")
            return result

        except Exception as e:
            duration = time.time() - start
            logger.error("agent_execution_failed", agent=self.name, error=str(e))
            audit_log("task_failed", agent=self.name, details=str(e), status="error")
            await event_bus.publish(Event(type="agent.failed", source=self.name,
                                          data={"agent": self.name, "error": str(e)}))
            return AgentResult(success=False, output="", error=str(e), agent=self.name, duration=duration)
        finally:
            self.is_active = False

    @abstractmethod
    async def run(self, task: str, context: dict) -> AgentResult:
        """Implement the actual agent logic."""
        ...

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "success_rate": self.successful_tasks / max(1, self.total_tasks),
        }


class AgentRegistry:
    """Registry for managing all agents. Supports hot-plugging."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        self._agents[agent.name] = agent
        logger.info("agent_registered", name=agent.name, capabilities=agent.capabilities)

    def unregister(self, name: str):
        if name in self._agents:
            del self._agents[name]
            logger.info("agent_unregistered", name=name)

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def get_by_capability(self, capability: str) -> list[BaseAgent]:
        return [a for a in self._agents.values() if capability in a.capabilities]

    def list_agents(self) -> list[dict]:
        return [a.get_status() for a in self._agents.values()]

    def get_all(self) -> dict[str, BaseAgent]:
        return self._agents.copy()
