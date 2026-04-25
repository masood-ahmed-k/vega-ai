"""
VEGA AI — Command Core
The central brain that connects all subsystems: agents, models, memory,
security, evolution, voice, automation, and the HUD.
"""

import asyncio
import time
from typing import Optional
import structlog

from core.event_bus import event_bus, Event
from core.logger import audit_log
from models.router import ModelRouter
from memory import MemoryManager
from agents import AgentRegistry
from agents.planner import PlannerAgent
from agents.research import ResearchAgent
from agents.resume import ResumeAgent
from agents.job import JobAgent
from agents.automation import AutomationAgent
from agents.study import StudyAgent
from agents.code import CodeAgent
from agents.email import EmailAgent
from agents.finance import FinanceAgent
from agents.health import HealthAgent
from agents.system_monitor import SystemMonitorAgent
from agents.memory_agent import MemoryAgent
from agents.video import VideoAgent
from agents.browser import BrowserAgent
from agents.image import ImageAgent
from memory.rag import LocalRAG
from security import SecurityManager
from core.evolution import EvolutionEngine
from skills import SkillLoader, SkillChain
from scheduler import Scheduler

logger = structlog.get_logger("vega.core")


class VEGACore:
    """The central command core of VEGA AI."""

    def __init__(self, config: dict):
        self.config = config
        self.start_time = time.time()

        # Initialize subsystems
        logger.info("initializing_subsystems")

        # Model Router
        self.router = ModelRouter(config.get("models", {}))

        # Memory System
        self.memory = MemoryManager(config.get("memory", {}))

        # Local File RAG (free, uses Ollama embeddings)
        rag_cfg = config.get("memory", {}).get("rag", {})
        rag_cfg.setdefault("ollama_host", config.get("models", {}).get("ollama_host", "http://localhost:11434"))
        self.rag = LocalRAG(rag_cfg) if rag_cfg.get("enabled", True) else None

        # Security
        self.security = SecurityManager(config.get("security", {}))

        # Agent Registry
        self.registry = AgentRegistry()

        # Register all built-in agents
        self._register_agents(config)

        # Planner (needs registry reference)
        self.planner = PlannerAgent(
            router=self.router, memory=self.memory,
            config=config.get("agents", {}).get("planner", {}),
            registry=self.registry
        )
        self.registry.register(self.planner)

        # Evolution Engine
        self.evolution = EvolutionEngine(
            config=config.get("evolution", {}),
            router=self.router,
            memory=self.memory,
            security=self.security
        )

        # Skill System
        self.skill_loader = SkillLoader(
            skill_dir=config.get("skills", {}).get("skill_dir", "./skills/builtins"),
            registry=self.registry
        )
        self.skill_chain = SkillChain(self.registry)

        # Scheduler
        self.scheduler = Scheduler(config.get("scheduler", {}))

        # Load skills
        if config.get("skills", {}).get("auto_load", True):
            self.skill_loader.load_all(router=self.router, memory=self.memory, config=config)

        # Subscribe to events
        event_bus.subscribe("agent.completed", self._on_agent_completed)
        event_bus.subscribe("system.alert", self._on_system_alert)

        logger.info("vega_core_initialized", agents=len(self.registry.list_agents()))

    def _register_agents(self, config: dict):
        """Register all built-in agents."""
        agents_config = config.get("agents", {})
        
        agents = [
            ResearchAgent(self.router, self.memory, agents_config.get("research", {})),
            ResumeAgent(self.router, self.memory),
            JobAgent(self.router, self.memory),
            AutomationAgent(self.router, self.memory, agents_config.get("automation", {})),
            StudyAgent(self.router, self.memory),
            CodeAgent(self.router, self.memory, agents_config.get("code", {})),
            EmailAgent(self.router, self.memory),
            FinanceAgent(self.router, self.memory),
            HealthAgent(self.router, self.memory),
            SystemMonitorAgent(self.router, self.memory),
            MemoryAgent(self.router, self.memory),
            VideoAgent(self.router, self.memory, config),
            BrowserAgent(self.router, self.memory, config),
            ImageAgent(self.router, self.memory, config),
        ]

        for agent in agents:
            self.registry.register(agent)

    async def process_command(self, command: str, force_agent: str | None = None) -> dict:
        """Process a user command through the planner or a specific agent."""
        logger.info("processing_command", command=command[:100])
        audit_log("command_received", details=command[:200])

        # Store in working memory
        self.memory.remember(f"User: {command}", role="user")

        start = time.time()

        try:
            if force_agent:
                # Direct agent execution
                agent = self.registry.get(force_agent)
                if agent:
                    result = await agent.execute(command, {})
                else:
                    result_text = f"Agent '{force_agent}' not found."
                    return {"success": False, "output": result_text, "agent": "system"}
            else:
                # Route through planner
                result = await self.planner.execute(command, {})

            duration = time.time() - start

            # Store response in memory
            self.memory.remember(f"VEGA: {result.output[:300]}", role="assistant", store_long_term=True)

            # Update XP/gamification
            await self._update_xp(result.success)

            response = {
                "success": result.success,
                "output": result.output,
                "agent": result.agent,
                "duration": round(duration, 2),
                "subtasks": result.subtasks_completed,
            }

            await event_bus.publish(Event(
                type="command.completed",
                data=response,
                source="core"
            ))

            return response

        except Exception as e:
            logger.error("command_failed", error=str(e))
            return {"success": False, "output": f"Error processing command: {str(e)}", "agent": "system"}

    async def stream_command(self, command: str):
        """Async generator for streaming chat responses token-by-token.
        Yields str tokens while generating, then yields a final dict result.
        Use this from the WebSocket handler for real-time UX."""
        logger.info("streaming_command", command=command[:80])
        self.memory.remember(f"User: {command}", role="user")

        # Inject recent memory context
        memories = self.memory.recall(command, n=3)
        mem_ctx = ""
        if memories.get("episodic"):
            snippets = [m["content"][:100] for m in memories["episodic"][:2]]
            mem_ctx = "\n\nRecent context: " + "; ".join(snippets)

        system = (
            "You are VEGA, an advanced autonomous AI assistant. "
            "Be concise, direct, and helpful. "
            "For tasks requiring real tools (browse web, generate images/video, read files), "
            "tell the user to use the dedicated buttons (BROWSE, IMAGE, VIDEO, FILES) in the UI. "
            "Otherwise respond naturally and helpfully."
        )

        full_text = ""
        start = time.time()
        try:
            async for token in self.router.stream_query(
                command + mem_ctx,
                task_type="conversation",
                system=system,
                temperature=0.7,
                max_tokens=1024,
            ):
                full_text += token
                yield token

        except Exception as e:
            error_msg = f"Stream error: {e}"
            full_text = error_msg
            yield error_msg

        duration = time.time() - start
        self.memory.remember(f"VEGA: {full_text[:300]}", role="assistant", store_long_term=True)
        await self._update_xp(bool(full_text))

        yield {
            "success": True,
            "output": full_text,
            "agent": "vega",
            "duration": round(duration, 2),
        }

    async def get_status(self) -> dict:
        """Get full system status."""
        uptime = time.time() - self.start_time

        # System resources
        system_stats = {}
        try:
            import psutil
            system_stats = {
                "cpu": psutil.cpu_percent(),
                "ram": psutil.virtual_memory().percent,
                "disk": round(psutil.disk_usage(".").percent, 1),
            }
        except ImportError:
            system_stats = {"cpu": 0, "ram": 0, "disk": 0}

        xp = self.memory.procedural.get_preference("xp", 0)
        level = self.memory.procedural.get_preference("level", 1)

        return {
            "name": "VEGA AI",
            "version": self.config.get("system", {}).get("version", "1.0.0"),
            "user": self.config.get("system", {}).get("user", "Hunter"),
            "uptime_seconds": round(uptime),
            "agents": self.registry.list_agents(),
            "skills_loaded": len(self.skill_loader.list_loaded()),
            "memory_count": self.memory.episodic.count(),
            "scheduler_tasks": len(self.scheduler.list_tasks()),
            "evolution_enabled": self.evolution.enabled,
            "xp": xp,
            "level": level,
            **system_stats,
        }

    async def _update_xp(self, success: bool):
        """Update gamification XP."""
        xp = self.memory.procedural.get_preference("xp", 0)
        level = self.memory.procedural.get_preference("level", 1)
        
        xp += 10 if success else 2
        
        # Level up every 100 XP
        new_level = (xp // 100) + 1
        if new_level > level:
            level = new_level
            await event_bus.publish(Event(type="gamification.level_up", data={"level": level}, source="core"))

        self.memory.procedural.set_preference("xp", xp)
        self.memory.procedural.set_preference("level", level)

    async def _on_agent_completed(self, event: Event):
        """Handle agent completion events."""
        data = event.data or {}
        if data.get("success") and self.router:
            self.router.record_feedback(
                task_type="general",
                model=self.router.select_model("general"),
                quality=0.7 if data.get("success") else 0.3
            )

    async def _on_system_alert(self, event: Event):
        """Handle system alerts."""
        alert = (event.data or {}).get("alert", "")
        logger.warning("system_alert", alert=alert)

    async def run_evolution_cycle(self):
        """Run a full self-evolution cycle."""
        if self.evolution.enabled:
            await self.evolution.auto_evolve()

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("shutting_down")
        self.scheduler.stop()
        # Create final snapshot
        self.security.snapshots.create_snapshot(reason="shutdown")
        logger.info("shutdown_complete")
