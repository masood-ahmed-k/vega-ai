"""
VEGA AI — REST API Server
External API for triggering VEGA actions, webhooks, and WebSocket communication.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import structlog

logger = structlog.get_logger("vega.api")


class TaskRequest(BaseModel):
    task: str
    agent: str | None = None
    context: dict = {}


class ApprovalAction(BaseModel):
    approval_id: str
    action: str  # "approve" or "deny"


class SkillGenRequest(BaseModel):
    name: str
    description: str
    capabilities: list[str]


class VideoRequest(BaseModel):
    prompt: str
    provider: str | None = None
    resolution: str = "1920x1080"
    duration: int = 5
    steps: int = 20


class ModelSwitchRequest(BaseModel):
    model: str | None = None  # null clears manual override


class ImageRequest(BaseModel):
    prompt: str
    provider: str | None = None


class BrowserRequest(BaseModel):
    task: str
    context: dict = {}


class RAGIndexRequest(BaseModel):
    path: str


class RAGSearchRequest(BaseModel):
    query: str
    k: int = 5


def _get_video_agent(vega_core):
    """Resolve the VideoAgent (may live in registry or skills)."""
    if hasattr(vega_core, "registry"):
        agent = vega_core.registry.get("video")
        if agent:
            return agent
        skill = vega_core.registry.get("video_generator")
        if skill and hasattr(skill, "get_agent"):
            return skill.get_agent()
    return None


def create_api(vega_core) -> FastAPI:
    """Create the FastAPI application connected to VEGA's core."""

    app = FastAPI(title="VEGA AI API", version="1.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ws_clients: list[WebSocket] = []

    async def broadcast(message: dict):
        for client in ws_clients[:]:
            try:
                await client.send_json(message)
            except Exception:
                ws_clients.remove(client)

    # ─── REST Endpoints ────────────────────────────────────────────────

    @app.get("/api")
    @app.get("/api/")
    async def api_root():
        return {"name": "VEGA AI", "version": "1.1.0", "status": "online"}

    @app.post("/api/task")
    async def execute_task(req: TaskRequest):
        result = await vega_core.process_command(req.task, force_agent=req.agent)
        await broadcast({"type": "task_result", "data": result})
        return result

    @app.get("/api/agents")
    async def list_agents():
        return {"agents": vega_core.registry.list_agents()}

    @app.get("/api/status")
    async def system_status():
        return await vega_core.get_status()

    @app.get("/api/memory/recall")
    async def recall_memory(query: str, n: int = 5):
        return vega_core.memory.recall(query, n=n)

    @app.post("/api/memory/store")
    async def store_memory(data: dict):
        text = data.get("text", "")
        vega_core.memory.remember(text, store_long_term=True)
        return {"status": "stored"}

    @app.get("/api/memory/chats")
    async def chat_history(limit: int = 50):
        """Return recent chat history from persistent store."""
        if hasattr(vega_core.memory, "chat"):
            return {"chats": vega_core.memory.chat.recent(limit)}
        return {"chats": []}

    @app.get("/api/memory/chats/search")
    async def chat_search(query: str, n: int = 10):
        """Semantic search across all past conversations."""
        if hasattr(vega_core.memory, "chat"):
            return {"results": vega_core.memory.chat.search(query, n)}
        # Fallback to episodic — normalize to chat schema so HUD can render it
        raw = vega_core.memory.episodic.recall(query, n_results=n)
        normalized = [
            {"content": r.get("text", r.get("content", "")), "metadata": r.get("metadata", {})}
            for r in (raw if isinstance(raw, list) else [])
        ]
        return {"results": normalized}

    @app.get("/api/tasks/history")
    async def task_history(limit: int = 20):
        return {"tasks": vega_core.memory.procedural.get_recent_tasks(limit)}

    @app.get("/api/scheduler/tasks")
    async def scheduled_tasks():
        return {"tasks": vega_core.scheduler.list_tasks()}

    @app.post("/api/approval")
    async def handle_approval(action: ApprovalAction):
        if action.action == "approve":
            success = vega_core.security.approval.approve(action.approval_id)
        else:
            success = vega_core.security.approval.deny(action.approval_id)
        return {"success": success}

    @app.get("/api/approvals/pending")
    async def pending_approvals():
        return {"pending": vega_core.security.approval.get_pending()}

    @app.get("/api/evolution/status")
    async def evolution_status():
        perf = await vega_core.evolution.analyze_performance()
        return perf

    @app.post("/api/evolution/evolve")
    async def evolve_agent(data: dict):
        agent_name = data.get("agent", "")
        result = await vega_core.evolution.evolve_agent(agent_name)
        return result

    @app.post("/api/skills/generate")
    async def generate_skill(req: SkillGenRequest):
        result = await vega_core.evolution.generate_skill(req.name, req.description, req.capabilities)
        return result

    @app.get("/api/snapshots")
    async def list_snapshots():
        return {"snapshots": vega_core.security.snapshots.list_snapshots()}

    @app.post("/api/snapshots/rollback")
    async def rollback_snapshot(data: dict):
        snapshot_id = data.get("snapshot_id", "")
        success = vega_core.security.snapshots.rollback(snapshot_id)
        return {"success": success}

    @app.get("/api/router/stats")
    async def router_stats():
        return vega_core.router.get_stats_summary()

    # ─── Model switcher ─────────────────────────────────────────────────

    @app.get("/api/models")
    async def list_models():
        """List all available AI models for HUD switcher."""
        models = []
        if hasattr(vega_core.router, "list_available_models"):
            models = vega_core.router.list_available_models()
        current = getattr(vega_core.router, "manual_override", None) \
                  or vega_core.router.config.get("default_local", "qwen3:8b")
        return {"models": models, "current": current}

    @app.post("/api/models/switch")
    async def switch_model(req: ModelSwitchRequest):
        """Switch the active AI model (HUD dropdown)."""
        if hasattr(vega_core.router, "set_manual_override"):
            vega_core.router.set_manual_override(req.model)
            await broadcast({"type": "model_switched", "data": {"model": req.model}})
            return {"success": True, "model": req.model}
        return {"success": False, "error": "Router does not support manual override"}

    # ─── Video generation endpoints ─────────────────────────────────────

    @app.get("/api/video/providers")
    async def list_video_providers():
        """List all text-to-video providers for HUD selector."""
        cfg = vega_core.config.get("video", {}).get("providers", {})
        providers = []
        for name, pc in cfg.items():
            providers.append({
                "name": name,
                "label": pc.get("label", name),
                "type": pc.get("type", "cloud"),
                "free": pc.get("free", False),
                "limit": pc.get("limit", "unlimited"),
            })
        default = vega_core.config.get("video", {}).get("default_provider", "huggingface")
        return {"providers": providers, "default": default}

    @app.post("/api/video/generate")
    async def generate_video(req: VideoRequest):
        agent = _get_video_agent(vega_core)
        if not agent:
            raise HTTPException(status_code=503, detail="Video agent not loaded")
        provider = req.provider or agent.default_provider
        job = await agent.create_job(req.prompt, provider, req.resolution, req.duration, req.steps)
        await broadcast({"type": "video_queued", "data": {"job_id": job.job_id}})
        return {"job_id": job.job_id, "status": job.status, "provider": job.provider}

    @app.get("/api/video/status/{job_id}")
    async def video_status(job_id: str):
        agent = _get_video_agent(vega_core)
        if not agent:
            raise HTTPException(status_code=503, detail="Video agent not loaded")
        job = agent.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return agent._job_to_dict(job)

    @app.get("/api/video/list")
    async def list_videos(limit: int = 50):
        agent = _get_video_agent(vega_core)
        if not agent:
            return {"videos": []}
        return {"videos": agent.list_jobs(limit)}

    @app.get("/api/video/download/{job_id}")
    async def download_video(job_id: str):
        agent = _get_video_agent(vega_core)
        if not agent:
            raise HTTPException(status_code=503, detail="Video agent not loaded")
        job = agent.get_job(job_id)
        if not job or not job.output_path:
            raise HTTPException(status_code=404, detail="Video not ready")
        path = Path(job.output_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Video file missing")
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    # ─── Image generation ──────────────────────────────────────────────

    @app.get("/api/image/providers")
    async def list_image_providers():
        cfg = vega_core.config.get("image", {}).get("providers", {})
        providers = [{"name": n, "label": pc.get("label", n), "type": pc.get("type", "local"),
                      "free": pc.get("free", True)} for n, pc in cfg.items()]
        default = vega_core.config.get("image", {}).get("default_provider", "flux_schnell")
        return {"providers": providers, "default": default}

    @app.post("/api/image/generate")
    async def generate_image(req: ImageRequest):
        agent = vega_core.registry.get("image")
        if not agent:
            raise HTTPException(status_code=503, detail="Image agent not loaded")
        # Pass provider only if it's a non-empty string (empty string → use agent default)
        ctx = {"provider": req.provider} if req.provider else {}
        res = await agent.execute(req.prompt, ctx)
        return {"success": res.success, "output": res.output, "data": res.data, "error": res.error}

    @app.get("/api/image/view/{filename}")
    async def view_image(filename: str):
        """Serve a generated image by filename so the HUD can display it inline."""
        agent = vega_core.registry.get("image")
        img_dir = Path(agent.output_dir) if agent else Path("./data/images")
        # Security: only serve files inside the images output directory
        safe_path = (img_dir / filename).resolve()
        if not str(safe_path).startswith(str(img_dir.resolve())):
            raise HTTPException(status_code=400, detail="Invalid path")
        if not safe_path.exists():
            raise HTTPException(status_code=404, detail="Image not found")
        media_type = "image/png" if filename.endswith(".png") else "image/jpeg"
        return FileResponse(safe_path, media_type=media_type)

    # ─── Browser agent ─────────────────────────────────────────────────

    @app.post("/api/browser/run")
    async def browser_run(req: BrowserRequest):
        agent = vega_core.registry.get("browser")
        if not agent:
            raise HTTPException(status_code=503, detail="Browser agent not loaded")
        res = await agent.execute(req.task, req.context or {})
        return {"success": res.success, "output": res.output, "data": res.data, "error": res.error}

    # ─── RAG over local files ──────────────────────────────────────────

    @app.post("/api/rag/index")
    async def rag_index(req: RAGIndexRequest):
        if not vega_core.rag:
            raise HTTPException(status_code=503, detail="RAG not enabled")
        p = Path(req.path)
        count = await (vega_core.rag.index_folder(p) if p.is_dir() else vega_core.rag.index_file(p))
        return {"indexed": count, "total_chunks": vega_core.rag.count()}

    @app.post("/api/rag/search")
    async def rag_search(req: RAGSearchRequest):
        if not vega_core.rag:
            raise HTTPException(status_code=503, detail="RAG not enabled")
        hits = await vega_core.rag.search(req.query, k=req.k)
        return {"results": hits, "total_chunks": vega_core.rag.count()}

    @app.get("/api/rag/status")
    async def rag_status():
        if not vega_core.rag:
            return {"enabled": False}
        return {"enabled": True, "total_chunks": vega_core.rag.count()}

    # ─── WebSocket ─────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        ws_clients.append(websocket)
        logger.info("ws_client_connected", total=len(ws_clients))

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "command":
                    task = data.get("task", "")

                    async def _run_cmd(t: str):
                        try:
                            async for chunk in vega_core.stream_command(t):
                                if isinstance(chunk, str):
                                    # Token — push immediately for real-time display
                                    await websocket.send_json({"type": "stream", "data": {"token": chunk}})
                                else:
                                    # Final result dict — signals completion
                                    await websocket.send_json({"type": "response", "data": chunk})
                                    await broadcast({"type": "activity", "data": {"task": t}})
                        except Exception as exc:
                            await websocket.send_json({"type": "response", "data": {
                                "success": False, "output": f"Command failed: {exc}", "agent": "system"
                            }})

                    asyncio.create_task(_run_cmd(task))

                elif msg_type == "status":
                    status = await vega_core.get_status()
                    await websocket.send_json({"type": "status", "data": status})

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            ws_clients.remove(websocket)
            logger.info("ws_client_disconnected", total=len(ws_clients))

    # Wire event_bus to broadcast — so video progress auto-pushes to HUD
    try:
        from core.event_bus import event_bus
        async def forward_event(event):
            if event.type.startswith("video."):
                await broadcast({"type": event.type, "data": event.data})
            elif event.type.startswith("agent."):
                await broadcast({"type": event.type, "data": event.data})
        event_bus.subscribe("*", forward_event)
    except Exception as e:
        logger.warning("event_bus_wire_failed", error=str(e))

    app.state.broadcast = broadcast
    app.state.ws_clients = ws_clients

    return app
