"""
VEGA AI — Memory System
Three-tier memory: Working (RAM), Episodic (ChromaDB), Procedural (SQLite), Knowledge Graph (NetworkX).
"""

import json
import time
import sqlite3
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger("vega.memory")


# ─── Working Memory (Short-term, in-RAM) ───────────────────────────────────────

@dataclass
class MemoryEntry:
    content: str
    role: str = "system"
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class WorkingMemory:
    """Short-term conversation context, kept in RAM."""

    def __init__(self, max_size: int = 50):
        self.entries: list[MemoryEntry] = []
        self.max_size = max_size

    def add(self, content: str, role: str = "system", metadata: dict | None = None):
        entry = MemoryEntry(content=content, role=role, metadata=metadata or {})
        self.entries.append(entry)
        if len(self.entries) > self.max_size:
            self.entries = self.entries[-self.max_size:]

    def get_context(self, limit: int = 20) -> list[dict]:
        return [{"role": e.role, "content": e.content} for e in self.entries[-limit:]]

    def clear(self):
        self.entries.clear()

    def search(self, keyword: str) -> list[MemoryEntry]:
        return [e for e in self.entries if keyword.lower() in e.content.lower()]


# ─── Episodic Memory (Long-term, Vector DB) ────────────────────────────────────

class EpisodicMemory:
    """Long-term semantic memory using ChromaDB for vector search."""

    def __init__(self, collection_name: str = "vega_episodes", persist_dir: str = "./data/chromadb"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import chromadb
                Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=self.persist_dir)
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                logger.error("chromadb_init_failed", error=str(e))
                self._client = None

    def store(self, text: str, metadata: dict | None = None):
        self._ensure_client()
        if not self._collection:
            return
        doc_id = f"ep_{int(time.time()*1000)}"
        meta = metadata or {}
        meta["timestamp"] = time.time()
        self._collection.add(documents=[text], metadatas=[meta], ids=[doc_id])
        logger.debug("episodic_stored", id=doc_id)

    def recall(self, query: str, n_results: int = 5) -> list[dict]:
        self._ensure_client()
        if not self._collection:
            return []
        try:
            results = self._collection.query(query_texts=[query], n_results=n_results)
            entries = []
            for i, doc in enumerate(results["documents"][0]):
                entries.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
            return entries
        except Exception as e:
            logger.error("episodic_recall_failed", error=str(e))
            return []

    def count(self) -> int:
        self._ensure_client()
        return self._collection.count() if self._collection else 0


# ─── Procedural Memory (Structured, SQLite) ────────────────────────────────────

class ProceduralMemory:
    """Stores learned workflows, user preferences, and structured knowledge."""

    def __init__(self, db_path: str = "./data/procedural.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    steps TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT,
                    agent TEXT,
                    result TEXT,
                    success INTEGER,
                    duration REAL,
                    timestamp REAL
                )
            """)

    def set_preference(self, key: str, value: Any):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?, ?)",
                         (key, json.dumps(value), time.time()))

    def get_preference(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save_workflow(self, name: str, steps: list[str]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflows (name, steps, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (name, json.dumps(steps), time.time(), time.time()))

    def get_workflow(self, name: str) -> list[str] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT steps FROM workflows WHERE name = ?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def record_task(self, task: str, agent: str, result: str, success: bool, duration: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO task_history (task, agent, result, success, duration, timestamp) VALUES (?,?,?,?,?,?)",
                         (task, agent, result, success, duration, time.time()))

    def get_recent_tasks(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM task_history ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "task": r[1], "agent": r[2], "result": r[3],
                 "success": bool(r[4]), "duration": r[5], "timestamp": r[6]} for r in rows]


# ─── Persistent Chat Memory ────────────────────────────────────────────────────

class ChatMemory:
    """Persistent chat history across restarts. Saves every user + VEGA turn
    to SQLite AND forwards to ChromaDB for semantic recall."""

    def __init__(self, db_path: str = "./data/chat_history.db", episodic: "EpisodicMemory | None" = None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.episodic = episodic
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    agent TEXT,
                    model TEXT,
                    timestamp REAL,
                    metadata TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_ts ON chats(timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_session ON chats(session_id)")

    def save(self, role: str, content: str, session_id: str = "default",
             agent: str = "", model: str = "", metadata: dict | None = None):
        """Save a single chat turn. Also embeds into ChromaDB for semantic search."""
        meta_json = json.dumps(metadata or {})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chats (session_id, role, content, agent, model, timestamp, metadata) VALUES (?,?,?,?,?,?,?)",
                (session_id, role, content, agent, model, time.time(), meta_json)
            )
        # Forward to semantic store
        if self.episodic:
            self.episodic.store(f"[{role}] {content}", metadata={
                "source": "chat", "role": role, "session_id": session_id,
                "agent": agent, "model": model,
            })

    def recent(self, limit: int = 50, session_id: str | None = None) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT id, session_id, role, content, agent, model, timestamp, metadata "
                    "FROM chats WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, session_id, role, content, agent, model, timestamp, metadata "
                    "FROM chats ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
        return [{
            "id": r[0], "session_id": r[1], "role": r[2], "content": r[3],
            "agent": r[4], "model": r[5], "timestamp": r[6],
            "metadata": json.loads(r[7]) if r[7] else {},
        } for r in rows]

    def search(self, query: str, n: int = 10) -> list[dict]:
        """Semantic search via ChromaDB, falls back to LIKE."""
        if self.episodic:
            results = self.episodic.recall(query, n_results=n)
            # Filter to chat source
            return [r for r in results if r.get("metadata", {}).get("source") == "chat"]
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM chats WHERE content LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?", (f"%{query}%", n)
            ).fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]

    def clear_session(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chats WHERE session_id=?", (session_id,))


# ─── Knowledge Graph ───────────────────────────────────────────────────────────

class KnowledgeGraph:
    """Entity-relationship graph for structured knowledge."""

    def __init__(self, persist_path: str = "./data/knowledge_graph.json"):
        self.persist_path = Path(persist_path)
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._graph = None

    def _ensure_graph(self):
        if self._graph is None:
            import networkx as nx
            if self.persist_path.exists() and self.persist_path.stat().st_size > 2:
                try:
                    with open(self.persist_path) as f:
                        data = json.load(f)
                    self._graph = nx.node_link_graph(data)
                except (json.JSONDecodeError, Exception):
                    self._graph = nx.DiGraph()
            else:
                self._graph = nx.DiGraph()

    def add_entity(self, entity: str, entity_type: str, attributes: dict | None = None):
        self._ensure_graph()
        attrs = attributes.copy() if attributes else {}
        attrs["entity_type"] = entity_type
        self._graph.add_node(entity, **attrs)
        self._save()

    def add_relation(self, source: str, target: str, relation: str, attributes: dict | None = None):
        self._ensure_graph()
        self._graph.add_edge(source, target, relation=relation, **(attributes or {}))
        self._save()

    def query_entity(self, entity: str) -> dict | None:
        self._ensure_graph()
        if entity in self._graph:
            node_data = dict(self._graph.nodes[entity])
            edges = []
            for _, target, data in self._graph.edges(entity, data=True):
                edges.append({"target": target, **data})
            for source, _, data in self._graph.in_edges(entity, data=True):
                edges.append({"source": source, **data})
            return {"entity": entity, "attributes": node_data, "relations": edges}
        return None

    def search(self, keyword: str) -> list[str]:
        self._ensure_graph()
        return [n for n in self._graph.nodes if keyword.lower() in n.lower()]

    def _save(self):
        import networkx as nx
        data = nx.node_link_data(self._graph)
        with open(self.persist_path, "w") as f:
            json.dump(data, f, indent=2, default=str)


# ─── Unified Memory Manager ───────────────────────────────────────────────────

class MemoryManager:
    """Unified interface to all memory tiers."""

    def __init__(self, config: dict):
        self.working = WorkingMemory(max_size=config.get("working_memory_size", 50))
        self.episodic = EpisodicMemory(
            collection_name=config.get("episodic", {}).get("collection", "vega_episodes")
        )
        self.procedural = ProceduralMemory(
            db_path=config.get("procedural", {}).get("db_path", "./data/procedural.db")
        )
        self.knowledge = KnowledgeGraph(
            persist_path=config.get("knowledge_graph", {}).get("persist_path", "./data/knowledge_graph.json")
        )
        # Persistent chat memory (all conversations, semantic search enabled)
        cp = config.get("chat_persistence", {})
        self.chat_enabled = cp.get("enabled", True)
        self.auto_recall = cp.get("auto_recall", True)
        self.recall_count = cp.get("recall_count", 5)
        self.chat = ChatMemory(
            db_path=cp.get("db_path", "./data/chat_history.db"),
            episodic=self.episodic,
        )

    def remember(self, text: str, role: str = "system", store_long_term: bool = False, metadata: dict | None = None):
        self.working.add(text, role=role, metadata=metadata)
        if store_long_term:
            self.episodic.store(text, metadata=metadata)

    def save_chat(self, role: str, content: str, session_id: str = "default",
                  agent: str = "", model: str = "", metadata: dict | None = None):
        """Persistent chat storage — call for every user turn and VEGA response."""
        if not self.chat_enabled:
            return
        self.working.add(content, role=role, metadata=metadata)
        self.chat.save(role, content, session_id=session_id, agent=agent, model=model, metadata=metadata)

    def build_context_with_recall(self, current_prompt: str, session_id: str = "default",
                                  limit: int = 20) -> str:
        """Assemble context: recent turns + semantically-related past chats."""
        parts = []
        if self.auto_recall and current_prompt:
            related = self.chat.search(current_prompt, n=self.recall_count)
            if related:
                parts.append("--- Relevant past context ---")
                for r in related:
                    parts.append(r.get("content", ""))
                parts.append("--- End past context ---\n")
        recent = self.chat.recent(limit=limit, session_id=session_id)
        for turn in reversed(recent):  # chronological
            parts.append(f"{turn['role']}: {turn['content']}")
        return "\n".join(parts)

    def recall(self, query: str, n: int = 5) -> dict:
        working = self.working.search(query)
        episodic = self.episodic.recall(query, n_results=n)
        knowledge = self.knowledge.search(query)
        return {
            "working": [e.content for e in working],
            "episodic": episodic,
            "knowledge_entities": knowledge,
        }

    def get_context_window(self, limit: int = 20) -> list[dict]:
        return self.working.get_context(limit)
