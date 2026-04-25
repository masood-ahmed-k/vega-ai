"""
VEGA AI — Video Agent (100% FREE providers)
2026 state-of-the-art text-to-video with 8 switchable providers.

Local (free, GPU):   Wan 2.2, CogVideoX-2B, LTX-Video, AnimateDiff
Cloud (free):        HuggingFace, ZSky AI, JSON2Video, Luma (5/mo free tier)

All videos upscale to Full HD (1920x1080) via ffmpeg.
NO paid services.
"""

import os
import time
import json
import uuid
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
import structlog
import httpx

from agents import BaseAgent, AgentResult
from core.event_bus import event_bus, Event

logger = structlog.get_logger("vega.video")


@dataclass
class VideoJob:
    job_id: str
    prompt: str
    provider: str
    status: str = "queued"
    progress: int = 0
    output_path: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    resolution: str = "1920x1080"
    duration: int = 5
    steps: int = 20


class VideoAgent(BaseAgent):
    name = "video"
    description = "Generates animated videos from text via 8 FREE providers (4 local + 4 cloud)"
    capabilities = ["text_to_video", "video_generation", "video_upscale", "video_library"]

    def __init__(self, router, memory, config: dict | None = None):
        super().__init__(router, memory, config)
        video_cfg = (config or {}).get("video", config or {})
        self.video_config = video_cfg
        self.output_dir = Path(video_cfg.get("output_dir", "./data/videos"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_provider = video_cfg.get("default_provider", "huggingface")
        self.default_resolution = video_cfg.get("default_resolution", "1920x1080")
        self.default_duration = video_cfg.get("default_duration", 5)
        self.default_fps = video_cfg.get("default_fps", 24)
        self.upscale_to_hd = video_cfg.get("upscale_to_hd", True)
        self.providers = video_cfg.get("providers", {})
        self.jobs: dict[str, VideoJob] = {}
        self._load_jobs()

    async def run(self, task: str, context: dict) -> AgentResult:
        provider = context.get("provider", self.default_provider)
        resolution = context.get("resolution", self.default_resolution)
        duration = context.get("duration", self.default_duration)
        job = await self.create_job(task, provider, resolution, duration)
        if context.get("async_mode", False):
            return AgentResult(success=True,
                               output=f"Video job {job.job_id} queued with {provider}.",
                               data={"job_id": job.job_id, "status": job.status})
        final = await self.wait_for_completion(job.job_id, timeout=900)
        if final.status == "done":
            return AgentResult(success=True,
                               output=f"Video generated: {final.output_path}",
                               data={"job_id": final.job_id, "output_path": final.output_path})
        return AgentResult(success=False, output=f"Video failed: {final.error}", error=final.error)

    async def create_job(self, prompt: str, provider: str, resolution: str, duration: int, steps: int = 20) -> VideoJob:
        job = VideoJob(
            job_id=f"vid_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            prompt=prompt, provider=provider, resolution=resolution, duration=duration, steps=steps,
        )
        self.jobs[job.job_id] = job
        self._save_jobs()
        asyncio.create_task(self._generate(job))
        await event_bus.publish(Event(type="video.queued", source="video",
                                      data={"job_id": job.job_id, "prompt": prompt, "provider": provider}))
        return job

    async def _generate(self, job: VideoJob):
        handlers = {
            "wan2": self._gen_wan2, "cogvideox": self._gen_cogvideox,
            "ltx": self._gen_ltx, "animatediff": self._gen_animatediff,
            "huggingface": self._gen_huggingface, "zsky": self._gen_zsky,
            "json2video": self._gen_json2video, "luma": self._gen_luma,
        }
        try:
            job.status = "generating"
            job.progress = 10
            self._save_jobs()
            await self._publish_progress(job)
            handler = handlers.get(job.provider)
            if not handler:
                raise ValueError(f"Unknown provider: {job.provider}")
            await handler(job)

            if self.upscale_to_hd and job.resolution == "1920x1080":
                job.status = "upscaling"
                job.progress = 85
                self._save_jobs()
                await self._publish_progress(job)
                await self._upscale_to_hd(job)

            job.status = "done"
            job.progress = 100
            job.finished_at = time.time()
            self._save_jobs()
            await event_bus.publish(Event(type="video.completed", source="video",
                                          data={"job_id": job.job_id, "output_path": job.output_path}))
            self.memory.remember(
                f"Generated video: {job.prompt} ({job.provider}) -> {job.output_path}",
                role="system", store_long_term=True,
                metadata={"agent": "video", "job_id": job.job_id, "provider": job.provider}
            )
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = time.time()
            self._save_jobs()
            logger.error("video_generation_failed", job_id=job.job_id, error=str(e))
            await event_bus.publish(Event(type="video.failed", source="video",
                                          data={"job_id": job.job_id, "error": str(e)}))

    # ─── Local providers (GPU, unlimited, no key) ─────────────────────

    async def _gen_wan2(self, job: VideoJob):
        await asyncio.to_thread(self._run_diffusers_pipeline, job, "wan2")
        job.progress = 75
        self._save_jobs()
        await self._publish_progress(job)

    async def _gen_cogvideox(self, job: VideoJob):
        await asyncio.to_thread(self._run_diffusers_pipeline, job, "cogvideox")
        job.progress = 75
        self._save_jobs()
        await self._publish_progress(job)

    async def _gen_ltx(self, job: VideoJob):
        await asyncio.to_thread(self._run_diffusers_pipeline, job, "ltx")
        job.progress = 75
        self._save_jobs()
        await self._publish_progress(job)

    async def _gen_animatediff(self, job: VideoJob):
        await asyncio.to_thread(self._run_diffusers_pipeline, job, "animatediff")
        job.progress = 75
        self._save_jobs()
        await self._publish_progress(job)

    def _run_diffusers_pipeline(self, job: VideoJob, provider_name: str):
        try:
            import torch
            from diffusers.utils import export_to_video
        except ImportError:
            raise RuntimeError(
                "Local video needs: pip install torch diffusers transformers accelerate imageio[ffmpeg]. "
                "Or switch provider to 'huggingface' / 'zsky' / 'json2video' (free cloud, no install)."
            )

        cfg = self.providers.get(provider_name, {})
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        frames = None

        # Progress callback — updates job.progress during denoising steps (10% -> 72%)
        def make_callback(total_steps: int):
            def _cb(pipe, step_index, timestep, callback_kwargs):
                pct = int(10 + (step_index / max(total_steps, 1)) * 62)
                job.progress = min(pct, 72)
                self._save_jobs()
                return callback_kwargs
            return _cb

        if provider_name == "wan2":
            # Wan 2.1 — use the -diffusers variant (the base .pth repo is NOT diffusers-compatible)
            # num_frames must be 4n+1: 17, 25, 33, 41, 49, 57, 65, 73, 81
            from diffusers import WanPipeline
            model_id = cfg.get("model_id_small", cfg.get("model_id"))
            # HF_HUB_OFFLINE=1 forces cache lookup by model_id with no network/redirect — uses
            # models--Wan-AI--Wan2.1-T2V-1.3B-diffusers directly without following HF's capital-D redirect
            _prev_offline = os.environ.get("HF_HUB_OFFLINE", "")
            os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                pipe = WanPipeline.from_pretrained(model_id, torch_dtype=dtype)
            except Exception:
                os.environ["HF_HUB_OFFLINE"] = _prev_offline  # not cached — allow download
                pipe = WanPipeline.from_pretrained(model_id, torch_dtype=dtype)
            finally:
                os.environ["HF_HUB_OFFLINE"] = _prev_offline
            pipe.enable_model_cpu_offload()
            # 5fps × duration, snapped to 4n+1 — exported at 5fps so duration matches request
            raw_frames = max(job.duration * 5, 17)
            num_frames = ((raw_frames - 1) // 4) * 4 + 1  # snap to 4n+1
            num_frames = min(num_frames, 25)  # cap at 25 = ~5s at 5fps
            num_steps = max(1, min(job.steps, 50))  # user-controlled, clamped 1-50
            result = pipe(
                prompt=job.prompt,
                height=480, width=832,
                num_frames=num_frames,
                num_inference_steps=num_steps,
                guidance_scale=5.0,
                callback_on_step_end=make_callback(num_steps),
            )
            frames = result.frames[0]

        elif provider_name == "cogvideox":
            from diffusers import CogVideoXPipeline
            _prev_offline = os.environ.get("HF_HUB_OFFLINE", "")
            os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                pipe = CogVideoXPipeline.from_pretrained(cfg["model_id"], torch_dtype=dtype)
            except Exception:
                os.environ["HF_HUB_OFFLINE"] = _prev_offline
                pipe = CogVideoXPipeline.from_pretrained(cfg["model_id"], torch_dtype=dtype)
            finally:
                os.environ["HF_HUB_OFFLINE"] = _prev_offline
            pipe.enable_model_cpu_offload()
            # CogVideoX expects multiples of 8 frames; keep it small for 8GB
            num_frames = min(max(job.duration * 4, 16), 32)
            num_steps = max(1, min(job.steps, 50))
            result = pipe(
                prompt=job.prompt,
                num_videos_per_prompt=1,
                num_inference_steps=num_steps,
                num_frames=num_frames,
                guidance_scale=6.0,
                generator=torch.Generator(device="cpu").manual_seed(42),
                callback_on_step_end=make_callback(num_steps),
            )
            frames = result.frames[0]

        elif provider_name == "ltx":
            from diffusers import LTXPipeline
            pipe = LTXPipeline.from_pretrained(cfg["model_id"], torch_dtype=dtype)
            pipe.enable_model_cpu_offload()
            # LTX requires height/width divisible by 32; frames divisible by 8
            num_frames = min(max((job.duration * 4 // 8) * 8, 8), 16)
            num_steps = max(1, min(job.steps, 50))
            result = pipe(
                prompt=job.prompt,
                height=480, width=704,
                num_frames=num_frames,
                num_inference_steps=num_steps,
                callback_on_step_end=make_callback(num_steps),
            )
            frames = result.frames[0]

        elif provider_name == "animatediff":
            from diffusers import AnimateDiffPipeline, MotionAdapter
            adapter = MotionAdapter.from_pretrained(cfg["model_id"], torch_dtype=dtype)
            pipe = AnimateDiffPipeline.from_pretrained(
                cfg["base_model"], motion_adapter=adapter, torch_dtype=dtype
            )
            pipe.enable_model_cpu_offload()
            if hasattr(pipe, "enable_vae_slicing"):
                pipe.enable_vae_slicing()
            num_frames = min(job.duration * 4, 16)
            num_steps = max(1, min(job.steps, 50))
            result = pipe(
                prompt=job.prompt,
                num_frames=num_frames,
                num_inference_steps=num_steps,
                guidance_scale=7.5,
                callback_on_step_end=make_callback(num_steps),
            )
            frames = result.frames[0]

        if frames is None:
            raise RuntimeError(f"No frames produced by {provider_name}")

        # Use native fps per provider — Wan2 at 5fps gives ~10s for 49 frames
        native_fps = {"wan2": 5, "cogvideox": 8, "ltx": 8, "animatediff": 16}
        fps = native_fps.get(provider_name, self.default_fps)
        out_path = self.output_dir / f"{job.job_id}.mp4"
        export_to_video(frames, str(out_path), fps=fps)
        job.output_path = str(out_path)
        # progress published by async caller (_gen_wan2 etc.) after thread returns

    # ─── Cloud providers (FREE) ──────────────────────────────────────

    async def _gen_huggingface(self, job: VideoJob):
        """HuggingFace — tries multiple models on the new Inference Providers router.

        Note: as of 2026, HF moved free T2V inference behind paid third-party providers
        (Fal/Replicate). This remains for compatibility; the truly free path is now
        LOCAL (wan2/cogvideox/ltx) or Luma/ZSky/JSON2Video signups.
        """
        api_key = os.getenv("HF_API_KEY", "")
        if not api_key:
            raise RuntimeError("HF_API_KEY not set. Free token: https://huggingface.co/settings/tokens")
        cfg = self.providers.get("huggingface", {})
        candidates = cfg.get("endpoints") or [cfg.get("endpoint")]
        candidates = [c for c in candidates if c]
        # Reasonable fallbacks to try
        if not candidates:
            candidates = [
                "https://router.huggingface.co/fal-ai/fal-ai/ltx-video",
                "https://api-inference.huggingface.co/models/Lightricks/LTX-Video",
            ]
        job.progress = 30
        self._save_jobs()
        await self._publish_progress(job)
        last_err = None
        async with httpx.AsyncClient(timeout=600) as client:
            for ep in candidates:
                try:
                    resp = await client.post(ep,
                                             headers={"Authorization": f"Bearer {api_key}"},
                                             json={"inputs": job.prompt})
                    if resp.status_code == 200 and resp.content and not resp.content.startswith(b'{"error"'):
                        out_path = self.output_dir / f"{job.job_id}.mp4"
                        out_path.write_bytes(resp.content)
                        job.output_path = str(out_path)
                        job.progress = 75
                        self._save_jobs()
                        await self._publish_progress(job)
                        return
                    last_err = f"{resp.status_code} at {ep}: {resp.text[:200]}"
                except Exception as e:
                    last_err = f"{ep}: {e}"
        raise RuntimeError(
            f"HuggingFace T2V unavailable ({last_err}). HF's free inference for video was "
            f"deprecated in 2025. Use a LOCAL provider (wan2/cogvideox/ltx/animatediff) after "
            f"running install_video_deps.bat, or sign up free at lumalabs.ai / zsky.ai / json2video.com."
        )

    async def _gen_zsky(self, job: VideoJob):
        """ZSky AI — FREE 1080p + audio, no credit card."""
        api_key = os.getenv("ZSKY_API_KEY", "")
        if not api_key:
            raise RuntimeError("ZSKY_API_KEY not set. Sign up free at https://zsky.ai/signup")
        cfg = self.providers.get("zsky", {})
        endpoint = cfg.get("endpoint", "https://api.zsky.ai/v1/videos")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"prompt": job.prompt, "resolution": "1080p",
                   "duration": job.duration, "with_audio": True}
        async with httpx.AsyncClient(timeout=900) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            gen_id = data.get("id") or data.get("video_id")
            if not gen_id:
                raise RuntimeError(f"ZSky returned no job id: {data}")
            for _ in range(180):
                await asyncio.sleep(5)
                status = await client.get(f"{endpoint}/{gen_id}", headers=headers)
                sd = status.json()
                state = sd.get("status", "")
                job.progress = min(75, 30 + self._poll_count(job) * 2)
                self._save_jobs()
                await self._publish_progress(job)
                if state in ("completed", "succeeded", "done"):
                    url = sd.get("video_url") or sd.get("output_url") or sd.get("url")
                    if url:
                        vid = await client.get(url)
                        out_path = self.output_dir / f"{job.job_id}.mp4"
                        out_path.write_bytes(vid.content)
                        job.output_path = str(out_path)
                        return
                elif state in ("failed", "error"):
                    raise RuntimeError(f"ZSky failed: {sd}")
        raise TimeoutError("ZSky timed out")

    async def _gen_json2video(self, job: VideoJob):
        """JSON2Video — FREE 600 seconds/month."""
        api_key = os.getenv("JSON2VIDEO_API_KEY", "")
        if not api_key:
            raise RuntimeError("JSON2VIDEO_API_KEY not set. Sign up free at https://json2video.com/get-api-key/")
        cfg = self.providers.get("json2video", {})
        endpoint = cfg.get("endpoint", "https://api.json2video.com/v2/movies")
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "resolution": "full-hd",
            "scenes": [{
                "elements": [
                    {"type": "text", "text": job.prompt, "duration": job.duration,
                     "settings": {"font-size": "48px"}}
                ]
            }]
        }
        async with httpx.AsyncClient(timeout=900) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            project_id = data.get("project")
            if not project_id:
                raise RuntimeError(f"JSON2Video no project id: {data}")
            for _ in range(120):
                await asyncio.sleep(5)
                status = await client.get(f"{endpoint}?project={project_id}", headers=headers)
                sd = status.json()
                movie = sd.get("movie", {})
                state = movie.get("status", "")
                job.progress = min(75, 30 + self._poll_count(job) * 2)
                self._save_jobs()
                await self._publish_progress(job)
                if state == "done":
                    url = movie.get("url")
                    if url:
                        vid = await client.get(url)
                        out_path = self.output_dir / f"{job.job_id}.mp4"
                        out_path.write_bytes(vid.content)
                        job.output_path = str(out_path)
                        return
                elif state == "error":
                    raise RuntimeError(f"JSON2Video failed: {movie}")
        raise TimeoutError("JSON2Video timed out")

    async def _gen_luma(self, job: VideoJob):
        """Luma Dream Machine — FREE 5 videos/month."""
        api_key = os.getenv("LUMA_API_KEY", "")
        if not api_key:
            raise RuntimeError("LUMA_API_KEY not set. Sign up free at https://lumalabs.ai/")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"prompt": job.prompt, "aspect_ratio": "16:9"}
        async with httpx.AsyncClient(timeout=900) as client:
            resp = await client.post("https://api.lumalabs.ai/dream-machine/v1/generations",
                                     headers=headers, json=payload)
            resp.raise_for_status()
            gen_id = resp.json().get("id")
            for _ in range(120):
                await asyncio.sleep(5)
                sr = await client.get(f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}",
                                      headers=headers)
                sd = sr.json()
                state = sd.get("state", "")
                job.progress = min(75, 30 + self._poll_count(job) * 3)
                self._save_jobs()
                await self._publish_progress(job)
                if state == "completed":
                    url = sd.get("assets", {}).get("video", "")
                    if url:
                        vid = await client.get(url)
                        out_path = self.output_dir / f"{job.job_id}.mp4"
                        out_path.write_bytes(vid.content)
                        job.output_path = str(out_path)
                        return
                elif state == "failed":
                    raise RuntimeError(f"Luma failed: {sd.get('failure_reason', 'unknown')}")
        raise TimeoutError("Luma timed out")

    # ─── Utilities ─────────────────────────────────────────────────

    async def _upscale_to_hd(self, job: VideoJob):
        try:
            src = job.output_path
            dst = str(self.output_dir / f"{job.job_id}_hd.mp4")
            cmd = ["ffmpeg", "-y", "-i", src,
                   "-vf", "scale=1920:1080:flags=lanczos",
                   "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                   "-pix_fmt", "yuv420p", dst]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()
            if proc.returncode == 0:
                job.output_path = dst
            else:
                logger.warning("ffmpeg_upscale_skipped", job_id=job.job_id)
        except Exception as e:
            logger.warning("upscale_failed", job_id=job.job_id, error=str(e))

    def _poll_count(self, job: VideoJob) -> int:
        return int((time.time() - job.started_at) / 5)

    async def _publish_progress(self, job: VideoJob):
        await event_bus.publish(Event(
            type="video.progress", source="video",
            data={"job_id": job.job_id, "status": job.status, "progress": job.progress}
        ))

    def get_job(self, job_id: str) -> VideoJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[dict]:
        items = sorted(self.jobs.values(), key=lambda j: j.started_at, reverse=True)[:limit]
        return [self._job_to_dict(j) for j in items]

    def _job_to_dict(self, j: VideoJob) -> dict:
        return {
            "job_id": j.job_id, "prompt": j.prompt, "provider": j.provider,
            "status": j.status, "progress": j.progress, "output_path": j.output_path,
            "error": j.error, "started_at": j.started_at, "finished_at": j.finished_at,
            "resolution": j.resolution, "duration": j.duration, "steps": j.steps,
        }

    async def wait_for_completion(self, job_id: str, timeout: int = 900) -> VideoJob:
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(f"Job {job_id} not found")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if job.status in ("done", "failed"):
                return job
            await asyncio.sleep(2)
        return job

    def _save_jobs(self):
        path = self.output_dir / "jobs.json"
        data = [self._job_to_dict(j) for j in self.jobs.values()]
        path.write_text(json.dumps(data, indent=2))

    def _load_jobs(self):
        path = self.output_dir / "jobs.json"
        if not path.exists():
            return
        try:
            for d in json.loads(path.read_text()):
                job = VideoJob(**d)
                # Reset stale in-progress jobs — they were killed on server restart
                if job.status in ("generating", "queued", "upscaling"):
                    job.status = "failed"
                    job.error = "Server restarted — job was interrupted. Please resubmit."
                    job.finished_at = time.time()
                self.jobs[job.job_id] = job
            self._save_jobs()
        except Exception as e:
            logger.warning("load_jobs_failed", error=str(e))
