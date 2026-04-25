"""
VEGA AI — Local File RAG
FAISS vector store + Ollama embeddings. 100% free, 100% local.

Index any folder (docs, code, PDFs). Ask VEGA questions; it recalls the right chunks.
"""

import os
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
import structlog
import httpx

logger = structlog.get_logger("vega.rag")


@dataclass
class Chunk:
    doc_id: str
    path: str
    text: str
    offset: int
    embedding: list[float] = field(default_factory=list)


class LocalRAG:
    """FAISS-free RAG — pure Python cosine + NumPy. Zero extra deps."""

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", True)
        self.index_dir = Path(config.get("index_dir", "./data/rag_index"))
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model = config.get("embedding_model", "nomic-embed-text")
        self.chunk_size = config.get("chunk_size", 512)
        self.overlap = config.get("chunk_overlap", 64)
        self.top_k = config.get("top_k", 5)
        self.ollama_host = config.get("ollama_host", "http://localhost:11434")
        self.chunks: list[Chunk] = []
        self._load_index()

    async def embed(self, text: str) -> list[float]:
        """Call Ollama /api/embeddings."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{self.ollama_host}/api/embeddings",
                                         json={"model": self.embedding_model, "prompt": text})
                resp.raise_for_status()
                return resp.json().get("embedding", [])
        except Exception as e:
            logger.warning("embed_failed", error=str(e))
            return []

    def _chunk_text(self, text: str) -> list[tuple[int, str]]:
        chunks = []
        i = 0
        while i < len(text):
            chunks.append((i, text[i:i + self.chunk_size]))
            i += self.chunk_size - self.overlap
        return chunks

    async def index_file(self, path: str | Path):
        p = Path(path)
        if not p.exists() or p.is_dir():
            return 0
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0
        doc_id = hashlib.md5(str(p.resolve()).encode()).hexdigest()[:12]
        # Remove existing chunks for this doc
        self.chunks = [c for c in self.chunks if c.doc_id != doc_id]
        added = 0
        for offset, piece in self._chunk_text(text):
            emb = await self.embed(piece)
            if not emb:
                continue
            self.chunks.append(Chunk(doc_id=doc_id, path=str(p.resolve()),
                                     text=piece, offset=offset, embedding=emb))
            added += 1
        self._save_index()
        logger.info("indexed", path=str(p), chunks=added)
        return added

    async def index_folder(self, folder: str | Path, extensions: list[str] | None = None):
        exts = extensions or [".txt", ".md", ".py", ".js", ".ts", ".json",
                              ".yaml", ".yml", ".html", ".css", ".rst", ".log"]
        f = Path(folder)
        total = 0
        if not f.exists():
            return 0
        for p in f.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                total += await self.index_file(p)
        return total

    async def search(self, query: str, k: int | None = None) -> list[dict]:
        if not self.chunks:
            return []
        k = k or self.top_k
        q_emb = await self.embed(query)
        if not q_emb:
            return []
        scored = []
        for c in self.chunks:
            if not c.embedding:
                continue
            score = self._cosine(q_emb, c.embedding)
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"score": round(s, 3), "path": c.path,
                 "text": c.text, "offset": c.offset}
                for s, c in scored[:k]]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _save_index(self):
        path = self.index_dir / "chunks.json"
        path.write_text(json.dumps([asdict(c) for c in self.chunks]))

    def _load_index(self):
        path = self.index_dir / "chunks.json"
        if not path.exists():
            return
        try:
            for d in json.loads(path.read_text()):
                self.chunks.append(Chunk(**d))
            logger.info("rag_index_loaded", chunks=len(self.chunks))
        except Exception as e:
            logger.warning("rag_load_failed", error=str(e))

    def count(self) -> int:
        return len(self.chunks)

    def clear(self):
        self.chunks = []
        self._save_index()
