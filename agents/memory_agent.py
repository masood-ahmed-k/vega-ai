"""
VEGA AI — Memory Agent
Manages long-term knowledge, stores and retrieves information, builds knowledge graph.
"""

from agents import BaseAgent, AgentResult


class MemoryAgent(BaseAgent):
    name = "memory_agent"
    description = "Stores and retrieves long-term knowledge, preferences, and relationships"
    capabilities = ["remember", "recall", "forget", "preferences", "knowledge"]

    async def run(self, task: str, context: dict) -> AgentResult:
        task_lower = task.lower()

        # Store command
        if any(kw in task_lower for kw in ["remember", "store", "save", "note"]):
            self.memory.remember(task, role="user", store_long_term=True,
                                 metadata={"type": "user_note"})
            return AgentResult(success=True, output=f"[OK] Stored in long-term memory: {task[:100]}")

        # Recall command
        elif any(kw in task_lower for kw in ["recall", "what do you know", "remember about", "search memory"]):
            query = task.replace("recall", "").replace("what do you know about", "").strip()
            results = self.memory.recall(query, n=5)
            
            output_parts = []
            if results["working"]:
                output_parts.append("Recent context:\n" + "\n".join(f"  - {w[:150]}" for w in results["working"][:3]))
            if results["episodic"]:
                output_parts.append("Long-term memories:\n" + "\n".join(
                    f"  - {e['content'][:150]}" for e in results["episodic"][:5]))
            if results["knowledge_entities"]:
                output_parts.append("Knowledge graph entities: " + ", ".join(results["knowledge_entities"][:5]))
            
            if not output_parts:
                output = "No memories found for that query."
            else:
                output = "\n\n".join(output_parts)
            
            return AgentResult(success=True, output=output, data=results)

        # Set preference
        elif "prefer" in task_lower or "set preference" in task_lower:
            self.memory.procedural.set_preference("user_note", task)
            return AgentResult(success=True, output=f"[OK] Preference noted: {task[:100]}")

        # General memory query — use AI to interpret
        else:
            response = await self.router.query(
                prompt=f"Memory query: {task}\n\nAvailable memory data: {self.memory.recall(task, n=3)}",
                system="You are a memory management assistant. Help the user store, retrieve, or organize their knowledge.",
                task_type="fast"
            )
            return AgentResult(success=True, output=response.text)
