"""
VEGA AI — Image Agent (FREE only)
Local: Flux.1-schnell, SDXL Turbo (RTX 4060 8GB)
Cloud: HuggingFace Inference API (free)

No paid providers.
"""

import os
import time
import uuid
import asyncio
from pathlib import Path
import structlog
import httpx

from agents import BaseAgent, AgentResult

logger = structlog.get_logger("vega.image")


class ImageAgent(BaseAgent):
    name = "image"
    description = "Generates images from text (Flux.1-schnell / SDXL Turbo local, or HF free cloud)"
    capabilities = ["text_to_image", "image_generation"]

    def __init__(self, router, memory, config: dict | None = None):
        super().__init__(router, memory, config)
        cfg = (config or {}).get("image", config or {})
        self.image_config = cfg
        self.output_dir = Path(cfg.get("output_dir", "./data/images"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_provider = cfg.get("default_provider", "flux_schnell")
        self.providers = cfg.get("providers", {})

    async def run(self, task: str, context: dict) -> AgentResult:
        provider = context.get("provider", self.default_provider)
        try:
            if provider in ("flux_schnell", "sdxl_turbo"):
                path = await asyncio.to_thread(self._gen_local, task, provider)
            elif provider == "huggingface":
                path = await self._gen_hf(task)
            else:
                return AgentResult(success=False, output=f"Unknown image provider: {provider}",
                                   error="unknown_provider")
            self.memory.remember(f"Generated image: {task} -> {path}", role="system",
                                 store_long_term=True, metadata={"agent": "image", "path": path})
            return AgentResult(success=True, output=f"Image saved: {path}",
                               data={"path": path, "provider": provider})
        except Exception as e:
            err_str = str(e)
            # Auto-fallback: if flux_schnell hits the HF gate (401/403/gated), retry with sdxl_turbo
            if provider == "flux_schnell" and any(k in err_str for k in ("401", "403", "gated", "restricted", "Access")):
                logger.warning("flux_gated_fallback_to_sdxl", error=err_str[:120])
                try:
                    path = await asyncio.to_thread(self._gen_local, task, "sdxl_turbo")
                    self.memory.remember(f"Generated image (sdxl_turbo fallback): {task} -> {path}",
                                         role="system", store_long_term=True,
                                         metadata={"agent": "image", "path": path})
                    return AgentResult(
                        success=True,
                        output=f"Image saved (used SDXL Turbo — Flux requires HF login, see README): {path}",
                        data={"path": path, "provider": "sdxl_turbo", "fallback": True},
                    )
                except Exception as e2:
                    logger.error("image_fallback_also_failed", error=str(e2))
                    return AgentResult(success=False,
                                       output=f"Image generation failed: {e2}", error=str(e2))
            logger.error("image_failed", error=err_str)
            return AgentResult(success=False, output=f"Image generation failed: {e}", error=err_str)

    def _gen_local(self, prompt: str, provider: str) -> str:
        try:
            import torch
        except ImportError:
            raise RuntimeError(
                "Local image needs: pip install torch diffusers transformers accelerate. "
                "Or set provider='huggingface' for free cloud."
            )
        cfg = self.providers.get(provider, {})
        model_id = cfg.get("model_id", "")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        if provider == "flux_schnell":
            from diffusers import FluxPipeline
            try:
                pipe = FluxPipeline.from_pretrained(model_id, torch_dtype=dtype)
            except Exception as e:
                if any(k in str(e) for k in ("401", "403", "gated", "restricted", "Access")):
                    raise RuntimeError(
                        f"401 Gated model: Flux.1-schnell requires HF login. "
                        f"Fix: (1) accept license at huggingface.co/black-forest-labs/FLUX.1-schnell "
                        f"(2) run: huggingface-cli login. "
                        f"Or use provider='sdxl_turbo' (no login needed)."
                    ) from e
                raise
            pipe.enable_model_cpu_offload()
            result = pipe(prompt, guidance_scale=0.0, num_inference_steps=4,
                          max_sequence_length=256).images[0]
        else:  # sdxl_turbo
            from diffusers import AutoPipelineForText2Image
            _prev_offline = os.environ.get("HF_HUB_OFFLINE", "")
            os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                pipe = AutoPipelineForText2Image.from_pretrained(
                    model_id, torch_dtype=dtype,
                    variant="fp16" if dtype == torch.float16 else None)
            except Exception:
                try:
                    os.environ["HF_HUB_OFFLINE"] = _prev_offline
                    pipe = AutoPipelineForText2Image.from_pretrained(
                        model_id, torch_dtype=dtype, variant="fp16" if dtype == torch.float16 else None)
                except Exception:
                    pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=dtype)
            finally:
                os.environ["HF_HUB_OFFLINE"] = _prev_offline
            pipe.to(device)
            result = pipe(prompt=prompt, num_inference_steps=1, guidance_scale=0.0).images[0]

        out_path = self.output_dir / f"img_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
        result.save(out_path)
        return str(out_path)

    async def _gen_hf(self, prompt: str) -> str:
        api_key = os.getenv("HF_API_KEY", "")
        if not api_key:
            raise RuntimeError("HF_API_KEY not set. Get free token: https://huggingface.co/settings/tokens")
        cfg = self.providers.get("huggingface", {})
        # Support both single endpoint and list of endpoints (with fallback)
        endpoints = cfg.get("endpoints") or ([cfg["endpoint"]] if cfg.get("endpoint") else [])
        if not endpoints:
            endpoints = [
                "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                "https://router.huggingface.co/fal-ai/fal-ai/flux/schnell",
                "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
            ]
        last_err = None
        async with httpx.AsyncClient(timeout=300) as client:
            for ep in endpoints:
                try:
                    resp = await client.post(ep,
                                             headers={"Authorization": f"Bearer {api_key}"},
                                             json={"inputs": prompt})
                    if resp.status_code == 200 and resp.content and not resp.content[:1] == b'{':
                        out_path = self.output_dir / f"img_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
                        out_path.write_bytes(resp.content)
                        return str(out_path)
                    last_err = f"{resp.status_code} at {ep}: {resp.text[:200]}"
                except Exception as e:
                    last_err = f"{ep}: {e}"
        raise RuntimeError(
            f"HuggingFace image API unavailable ({last_err}). "
            f"HF removed free image inference in 2025. "
            f"Use local providers instead: run install_video_deps.bat, then select 'flux_schnell' or 'sdxl_turbo'."
        )
