"""
VEGA AI - Multi-Model Intelligence Router
Auto-selects the best AI model per task. Learns from performance over time.
Supports OpenAI, Claude, Gemini, and local Ollama models (Qwen3 + others).

Hardware-optimized for RTX 4060 + 32GB RAM + i7-13650HX.
"""

import time
import json
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import structlog
import httpx

logger = structlog.get_logger("vega.router")


@dataclass
class ModelResponse:
    text: str
    model: str
    provider: str
    latency: float
    tokens_used: int = 0
    cost_estimate: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class ModelStats:
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    avg_latency: float = 0.0
    total_latency: float = 0.0
    score: float = 0.5

    def update(self, latency: float, success: bool, quality: float = 0.5):
        self.total_calls += 1
        if success:
            self.successes += 1
        else:
            self.failures += 1
        self.total_latency += latency
        self.avg_latency = self.total_latency / self.total_calls
        self.score = 0.9 * self.score + 0.1 * quality


class ModelRouter:
    """Routes tasks to the optimal AI model based on task type, cost, and learned performance."""

    TASK_MODEL_MAP = {
        # qwen3:8b fits fully in 8GB VRAM — fast responses
        # qwen3:30b-a3b used only for coding/research (MoE, more efficient than 32b)
        "reasoning": "qwen3:8b",
        "coding": "qwen3:30b-a3b",
        "research": "qwen3:30b-a3b",
        "fast": "qwen3:8b",
        "creative": "qwen3:8b",
        "analysis": "qwen3:8b",
        "conversation": "qwen3:8b",
        "summarization": "qwen3:8b",
    }

    PROVIDER_MAP = {
        # OpenAI
        "gpt-4o": "openai",
        "gpt-4o-mini": "openai",
        "gpt-4-turbo": "openai",
        # Anthropic
        "claude-sonnet-4-20250514": "anthropic",
        "claude-opus-4-20250514": "anthropic",
        # Google
        "gemini-pro": "google",
        "gemini-1.5-flash": "google",
        # Ollama — Qwen3 lineup
        "qwen3:32b": "ollama",
        "qwen3:30b-a3b": "ollama",
        "qwen3:14b": "ollama",
        "qwen3:8b": "ollama",
        "qwen3:4b": "ollama",
        # Ollama — legacy fallback
        "llama3:latest": "ollama",
        "llama3": "ollama",
        "llama3.2:3b": "ollama",
        "mistral": "ollama",
        "mistral:7b": "ollama",
        "mixtral:8x7b": "ollama",
        "codellama": "ollama",
        "phi3": "ollama",
        "phi3:mini": "ollama",
        "deepseek-r1:14b": "ollama",
    }

    def __init__(self, config: dict):
        self.config = config
        self.stats: dict[str, dict[str, ModelStats]] = {}
        self.fallback_chain = config.get("fallback_chain", ["qwen3:8b", "llama3:latest"])
        self.cost_preference = config.get("cost_preference", "local_first")
        self.stats_path = Path("./data/router_stats.json")

        # Hardware optimization settings — push all layers to GPU, spill to RAM
        self.hardware = config.get("hardware", {})
        self.num_gpu = self.hardware.get("num_gpu", 99)
        self.num_ctx = self.hardware.get("num_ctx", 8192)
        self.num_thread = self.hardware.get("num_thread", 14)
        self.num_batch = self.hardware.get("num_batch", 512)
        self.keep_alive = self.hardware.get("keep_alive", "30m")

        # Manual override (set from HUD)
        self.manual_override: str | None = None

        self._load_stats()

    def set_manual_override(self, model: str | None):
        """HUD model switcher — force a specific model regardless of task type."""
        self.manual_override = model
        if model:
            logger.info("manual_model_override_set", model=model)
        else:
            logger.info("manual_model_override_cleared")

    def select_model(self, task_type: str, force_model: str | None = None) -> str:
        if force_model:
            return force_model
        if self.manual_override:
            return self.manual_override

        if task_type in self.stats:
            task_stats = self.stats[task_type]
            best_model = None
            best_score = -1
            for model, s in task_stats.items():
                if s.total_calls >= 5 and s.score > best_score:
                    adjusted = s.score
                    if self.cost_preference == "local_first" and self.PROVIDER_MAP.get(model) == "ollama":
                        adjusted *= 1.3
                    elif self.cost_preference == "quality_first" and self.PROVIDER_MAP.get(model) != "ollama":
                        adjusted *= 1.1
                    if adjusted > best_score:
                        best_score = adjusted
                        best_model = model
            if best_model and best_score > 0.6:
                logger.info("model_selected_learned", task=task_type, model=best_model, score=best_score)
                return best_model

        routing = self.config.get("routing", {})
        model = routing.get(task_type, self.TASK_MODEL_MAP.get(task_type, self.config.get("default_local", "qwen3:8b")))
        logger.info("model_selected_default", task=task_type, model=model)
        return model

    async def preload_model(self, model: str | None = None):
        """Warm up an Ollama model so the first real query is fast."""
        target = model or self.config.get("default_local", "qwen3:8b")
        if self.PROVIDER_MAP.get(target) != "ollama":
            return
        try:
            host = self.config.get("ollama_host", "http://localhost:11434")
            async with httpx.AsyncClient(timeout=300) as client:
                await client.post(f"{host}/api/generate", json={
                    "model": target, "prompt": "", "keep_alive": self.keep_alive,
                })
            logger.info("model_preloaded", model=target)
        except Exception as e:
            logger.warning("model_preload_failed", model=target, error=str(e))

    async def query(self, prompt: str, task_type: str = "reasoning",
                    system: str = "", force_model: str | None = None,
                    temperature: float = 0.7, max_tokens: int = 2000) -> ModelResponse:

        model = self.select_model(task_type, force_model)
        provider = self.PROVIDER_MAP.get(model, "ollama")

        models_to_try = [model] + [m for m in self.fallback_chain if m != model]

        for attempt_model in models_to_try:
            attempt_provider = self.PROVIDER_MAP.get(attempt_model, "ollama")
            try:
                start = time.time()
                response = await self._call_provider(attempt_provider, attempt_model, prompt, system, temperature, max_tokens)
                latency = time.time() - start
                response.latency = latency
                self._record_stats(task_type, attempt_model, latency, True)
                if attempt_model != model:
                    logger.warning("model_fallback_used", original=model, fallback=attempt_model)
                return response

            except Exception as e:
                logger.error("model_call_failed", model=attempt_model, error=str(e))
                self._record_stats(task_type, attempt_model, 0, False)
                continue

        return ModelResponse(text="All models failed. Please check your API keys and network.", model=model,
                             provider=provider, latency=0, success=False, error="All models exhausted")

    async def stream_query(self, prompt: str, task_type: str = "conversation",
                           system: str = "", temperature: float = 0.7, max_tokens: int = 1024):
        """Async generator: yields str tokens from Ollama in real time.
        Falls back to a single string yield for cloud providers."""
        model = self.select_model(task_type)
        provider = self.PROVIDER_MAP.get(model, "ollama")

        if provider != "ollama":
            # Cloud providers don't stream — yield full text at once
            try:
                resp = await self.query(prompt, task_type, system,
                                        temperature=temperature, max_tokens=max_tokens)
                yield resp.text
            except Exception as e:
                yield f"Error: {e}"
            return

        host = self.config.get("ollama_host", "http://localhost:11434")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_gpu": self.num_gpu,
                "num_ctx": self.num_ctx,
                "num_thread": self.num_thread,
                "num_batch": self.num_batch,
            },
        }
        if system:
            payload["system"] = system

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{host}/api/generate", json=payload) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
                            if chunk.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
            self._record_stats(task_type, model, time.time() - start, True)
        except Exception as e:
            logger.error("stream_query_failed", model=model, error=str(e))
            self._record_stats(task_type, model, 0, False)
            yield f"\n[Model error: {e}. Is Ollama running?]"

    async def _call_provider(self, provider: str, model: str, prompt: str,
                             system: str, temperature: float, max_tokens: int) -> ModelResponse:
        if provider == "openai":
            return await self._call_openai(model, prompt, system, temperature, max_tokens)
        elif provider == "anthropic":
            return await self._call_anthropic(model, prompt, system, temperature, max_tokens)
        elif provider == "google":
            return await self._call_google(model, prompt, system, temperature, max_tokens)
        elif provider == "ollama":
            return await self._call_ollama(model, prompt, system, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def _call_openai(self, model, prompt, system, temperature, max_tokens) -> ModelResponse:
        import openai
        client = openai.AsyncOpenAI()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        return ModelResponse(text=text, model=model, provider="openai", latency=0, tokens_used=tokens)

    async def _call_anthropic(self, model, prompt, system, temperature, max_tokens) -> ModelResponse:
        import anthropic
        client = anthropic.AsyncAnthropic()
        kwargs = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "user", "content": prompt}]}
        if system:
            kwargs["system"] = system
        resp = await client.messages.create(**kwargs)
        text = resp.content[0].text if resp.content else ""
        tokens = (resp.usage.input_tokens + resp.usage.output_tokens) if resp.usage else 0
        return ModelResponse(text=text, model=model, provider="anthropic", latency=0, tokens_used=tokens)

    async def _call_google(self, model, prompt, system, temperature, max_tokens) -> ModelResponse:
        import google.generativeai as genai
        gen_model = genai.GenerativeModel(model)
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        resp = await asyncio.to_thread(gen_model.generate_content, full_prompt)
        text = resp.text if resp else ""
        return ModelResponse(text=text, model=model, provider="google", latency=0)

    async def _call_ollama(self, model, prompt, system, temperature, max_tokens) -> ModelResponse:
        host = self.config.get("ollama_host", "http://localhost:11434")
        # Hardware-optimized options — GPU layers maxed, RAM overflow, CPU threads maxed
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_gpu": self.num_gpu,
            "num_ctx": self.num_ctx,
            "num_thread": self.num_thread,
            "num_batch": self.num_batch,
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{host}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = data.get("response", "")
        return ModelResponse(text=text, model=model, provider="ollama", latency=0)

    def _record_stats(self, task_type: str, model: str, latency: float, success: bool, quality: float = 0.5):
        if task_type not in self.stats:
            self.stats[task_type] = {}
        if model not in self.stats[task_type]:
            self.stats[task_type][model] = ModelStats()
        self.stats[task_type][model].update(latency, success, quality)
        self._save_stats()

    def record_feedback(self, task_type: str, model: str, quality: float):
        if task_type in self.stats and model in self.stats[task_type]:
            self.stats[task_type][model].score = 0.7 * self.stats[task_type][model].score + 0.3 * quality
            self._save_stats()

    def _save_stats(self):
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for task, models in self.stats.items():
            data[task] = {}
            for model, s in models.items():
                data[task][model] = {"total_calls": s.total_calls, "successes": s.successes,
                                     "failures": s.failures, "avg_latency": s.avg_latency, "score": s.score}
        with open(self.stats_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_stats(self):
        if self.stats_path.exists():
            with open(self.stats_path) as f:
                data = json.load(f)
            for task, models in data.items():
                self.stats[task] = {}
                for model, s in models.items():
                    ms = ModelStats(**s)
                    self.stats[task][model] = ms

    def get_stats_summary(self) -> dict:
        summary = {}
        for task, models in self.stats.items():
            summary[task] = {model: {"calls": s.total_calls, "score": round(s.score, 3),
                                     "avg_latency": round(s.avg_latency, 2)}
                             for model, s in models.items()}
        return summary

    def list_available_models(self) -> list[dict]:
        """Return all configured models (for HUD switcher)."""
        available = self.config.get("available", [])
        if available:
            return available
        # Fallback: derive from PROVIDER_MAP
        return [{"name": m, "label": m, "type": "local" if p == "ollama" else "cloud"}
                for m, p in self.PROVIDER_MAP.items()]
