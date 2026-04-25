"""
VEGA AI — Skill System
Hot-loadable plugin skills with auto-discovery and skill chaining.
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Optional
import structlog

from agents import BaseAgent, AgentRegistry

logger = structlog.get_logger("vega.skills")


class SkillLoader:
    """Discovers and loads skill plugins from the skills directory."""

    def __init__(self, skill_dir: str = "./skills/builtins", registry: AgentRegistry = None):
        self.skill_dir = Path(skill_dir)
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        self.loaded_skills: dict[str, str] = {}  # name -> file path

    def discover(self) -> list[str]:
        """Find all skill files in the skills directory."""
        skills = []
        for f in self.skill_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            skills.append(str(f))
        return skills

    def load_skill(self, path: str, router=None, memory=None, config=None) -> BaseAgent | None:
        """Load a single skill from a Python file.

        Only instantiates classes DEFINED in the skill module (ignoring
        BaseAgent subclasses that were merely imported — e.g. `VideoAgent`
        imported by `video_generator.py` must not be picked up).
        """
        path = Path(path)
        if not path.exists():
            logger.error("skill_not_found", path=str(path))
            return None

        try:
            module_name = f"skills.{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find the agent class DEFINED in this module (not imported).
            # We match by module attribute AND fall back to checking __module__.
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not (isinstance(attr, type) and issubclass(attr, BaseAgent)
                        and attr is not BaseAgent and hasattr(attr, 'name')):
                    continue
                # Skip classes imported from another module (e.g. agents.video.VideoAgent)
                if getattr(attr, "__module__", "") != module_name:
                    continue
                # Try instantiating with config; fall back for 2-arg skills.
                try:
                    agent = attr(router=router, memory=memory, config=config)
                except TypeError:
                    agent = attr(router=router, memory=memory)
                self.loaded_skills[agent.name] = str(path)
                if self.registry:
                    self.registry.register(agent)
                logger.info("skill_loaded", name=agent.name, path=str(path))
                return agent

            logger.warning("no_agent_class_found", path=str(path))
            return None

        except Exception as e:
            logger.error("skill_load_failed", path=str(path), error=str(e))
            return None

    def load_all(self, router=None, memory=None, config=None) -> list[BaseAgent]:
        """Discover and load all skills."""
        loaded = []
        for path in self.discover():
            agent = self.load_skill(path, router=router, memory=memory, config=config)
            if agent:
                loaded.append(agent)
        logger.info("skills_loaded", count=len(loaded))
        return loaded

    def reload_skill(self, name: str, router=None, memory=None) -> BaseAgent | None:
        """Hot-reload a skill by name."""
        if name in self.loaded_skills:
            path = self.loaded_skills[name]
            # Unregister old version
            if self.registry:
                self.registry.unregister(name)
            # Remove from sys.modules
            module_name = f"skills.{Path(path).stem}"
            if module_name in sys.modules:
                del sys.modules[module_name]
            # Reload
            return self.load_skill(path, router=router, memory=memory)
        return None

    def list_loaded(self) -> list[dict]:
        return [{"name": name, "path": path} for name, path in self.loaded_skills.items()]


class SkillChain:
    """Chains multiple skills together, feeding output of one into the next."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    async def execute_chain(self, steps: list[dict]) -> list[dict]:
        """Execute a chain of skills sequentially.
        
        steps: [{"agent": "research", "task": "..."}, {"agent": "code", "task": "..."}]
        Each step can reference previous output with {prev_output}
        """
        results = []
        prev_output = ""

        for step in steps:
            agent_name = step["agent"]
            task = step["task"].replace("{prev_output}", prev_output)

            agent = self.registry.get(agent_name)
            if agent:
                result = await agent.execute(task, {"prev_output": prev_output})
                results.append({"agent": agent_name, "output": result.output, "success": result.success})
                prev_output = result.output
            else:
                results.append({"agent": agent_name, "output": f"Agent {agent_name} not found", "success": False})

        return results
