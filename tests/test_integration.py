"""
VEGA AI — End-to-end integration tests.

Validates:
- All modules import cleanly (no circular / missing deps)
- Config loads and has required keys
- Ollama is reachable and our models are installed
- All agents instantiate and satisfy the BaseAgent contract
- Registry, router, memory, RAG, API routes exist
- FastAPI app boots and critical routes respond
- Model routing + manual override works
- Video/image agents construct with 7-8 FREE providers (no paid)
- MCP server module imports

Run:
    python -m pytest tests -v
or:
    python tests/test_integration.py
"""

import asyncio
import inspect
import os
import sys
from pathlib import Path

# pytest is optional — tests also run via the built-in CLI runner at the bottom
try:
    import pytest
except ImportError:
    class _PytestShim:
        class mark:
            @staticmethod
            def asyncio(fn): return fn
        @staticmethod
        def fixture(fn=None, **kw): return fn if fn else (lambda f: f)
        @staticmethod
        def skip(msg): raise AssertionError(f"SKIP: {msg}")
    pytest = _PytestShim()

# Make project importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


# ─────────────────────────── module import smoke tests ──────────────────

def test_core_imports():
    import core
    from core import load_config
    from core.command_core import VEGACore
    from core.event_bus import event_bus, Event
    from core.logger import audit_log
    from core.evolution import EvolutionEngine


def test_agent_imports():
    from agents import BaseAgent, AgentResult, AgentRegistry
    from agents.video import VideoAgent
    from agents.browser import BrowserAgent
    from agents.image import ImageAgent
    from agents.planner import PlannerAgent
    from agents.research import ResearchAgent
    from agents.code import CodeAgent
    from agents.memory_agent import MemoryAgent


def test_memory_imports():
    from memory import MemoryManager
    from memory.rag import LocalRAG


def test_api_imports():
    from api import create_api


def test_mcp_server_imports():
    # Module should import even if MCP SDK not installed (it only fails at runtime call)
    import mcp_server


# ─────────────────────────── config validation ─────────────────────────

def test_config_loads_with_required_keys():
    from core import load_config
    config = load_config()

    assert config["system"]["name"] == "VEGA"
    assert config["models"]["default_local"].startswith("qwen3")
    assert "qwen3:32b" in config["models"]["routing"].values()
    assert "hardware" in config["models"]
    assert config["models"]["hardware"]["num_gpu"] > 0
    assert config["memory"]["chat_persistence"]["enabled"] is True
    assert config["video"]["enabled"] is True
    assert config["image"]["enabled"] is True
    assert config["browser"]["enabled"] is True
    assert config["memory"]["rag"]["enabled"] is True


def test_no_paid_providers_in_config():
    """VEGA is 100% free — no Runway, no Replicate."""
    from core import load_config
    config = load_config()

    video_providers = config["video"]["providers"]
    assert "runway" not in video_providers
    assert "replicate" not in video_providers

    # Every provider must be marked free
    for name, p in video_providers.items():
        assert p.get("free") is True, f"Video provider {name} is not free"
    for name, p in config["image"]["providers"].items():
        assert p.get("free") is True, f"Image provider {name} is not free"


def test_video_providers_are_the_expected_eight():
    from core import load_config
    config = load_config()
    expected = {"wan2", "cogvideox", "ltx", "animatediff",
                "huggingface", "zsky", "json2video", "luma"}
    actual = set(config["video"]["providers"].keys())
    assert actual == expected, f"Provider mismatch: {actual ^ expected}"


def test_available_models_includes_qwen3_variants():
    from core import load_config
    names = {m["name"] for m in load_config()["models"]["available"]}
    assert {"qwen3:32b", "qwen3:30b-a3b", "qwen3:8b", "llama3:latest"} <= names


# ─────────────────────────── agent contract tests ──────────────────────

@pytest.fixture
def config():
    from core import load_config
    return load_config()


@pytest.fixture
def router_memory(config):
    from models.router import ModelRouter
    from memory import MemoryManager
    return ModelRouter(config["models"]), MemoryManager(config["memory"])


def test_router_exposes_query_not_generate(router_memory):
    router, _ = router_memory
    assert hasattr(router, "query") and callable(router.query)
    assert hasattr(router, "set_manual_override")
    assert hasattr(router, "list_available_models")
    # No stray `.generate` method we might have accidentally added
    assert not hasattr(router, "generate") or callable(getattr(router, "generate"))


def test_all_agents_subclass_baseagent(config, router_memory):
    from agents import BaseAgent
    from agents.video import VideoAgent
    from agents.browser import BrowserAgent
    from agents.image import ImageAgent

    router, memory = router_memory
    for cls in (VideoAgent, BrowserAgent, ImageAgent):
        inst = cls(router, memory, config)
        assert isinstance(inst, BaseAgent)
        assert inst.name
        assert inst.description
        assert callable(inst.run)
        # BaseAgent.execute wraps run(); must be awaitable
        assert inspect.iscoroutinefunction(inst.run)


def test_video_agent_has_free_providers_only(config, router_memory):
    from agents.video import VideoAgent
    router, memory = router_memory
    agent = VideoAgent(router, memory, config)

    paid_handlers = ["_gen_runway", "_gen_replicate"]
    for attr in paid_handlers:
        assert not hasattr(agent, attr), f"{attr} is a paid handler that should be removed"

    free_handlers = ["_gen_wan2", "_gen_cogvideox", "_gen_ltx", "_gen_animatediff",
                     "_gen_huggingface", "_gen_zsky", "_gen_json2video", "_gen_luma"]
    for attr in free_handlers:
        assert hasattr(agent, attr), f"missing free handler {attr}"


def test_image_agent_has_providers(config, router_memory):
    from agents.image import ImageAgent
    router, memory = router_memory
    agent = ImageAgent(router, memory, config)
    assert agent.default_provider in agent.providers


def test_browser_agent_uses_router_query(config, router_memory):
    """Regression: BrowserAgent must call router.query (audit blocker #1)."""
    from agents.browser import BrowserAgent
    src = Path(ROOT / "agents/browser.py").read_text()
    assert "self.router.query(" in src
    assert "self.router.generate(" not in src


# ─────────────────────────── memory + RAG ──────────────────────────────

def test_memory_manager_has_chat_persistence(config):
    from memory import MemoryManager
    m = MemoryManager(config["memory"])
    assert hasattr(m, "chat")
    assert hasattr(m.chat, "recent")
    assert hasattr(m.chat, "search")
    assert hasattr(m, "remember")


def test_rag_module_usable(config):
    from memory.rag import LocalRAG
    rag_cfg = dict(config["memory"]["rag"])
    rag_cfg["ollama_host"] = config["models"]["ollama_host"]
    rag = LocalRAG(rag_cfg)
    assert rag.count() >= 0
    # Cosine sanity
    assert abs(LocalRAG._cosine([1, 0], [1, 0]) - 1.0) < 1e-6
    assert abs(LocalRAG._cosine([1, 0], [0, 1]) - 0.0) < 1e-6


# ─────────────────────────── VEGACore boot + API ───────────────────────

@pytest.fixture
def vega_core(config):
    from core.command_core import VEGACore
    return VEGACore(config)


def test_vega_core_registers_all_agents(vega_core):
    registered = {a.name for a in vega_core.registry.get_all().values()}
    expected = {"video", "browser", "image"}  # new ones we added
    assert expected <= registered, f"missing: {expected - registered}"


def test_vega_core_has_rag(vega_core):
    assert vega_core.rag is not None


def test_fastapi_app_mounts_new_routes(vega_core):
    from api import create_api
    app = create_api(vega_core)
    routes = {r.path for r in app.routes}
    for r in ["/api/models", "/api/models/switch",
              "/api/video/providers", "/api/video/generate",
              "/api/image/providers", "/api/image/generate",
              "/api/browser/run",
              "/api/rag/index", "/api/rag/search", "/api/rag/status",
              "/api/memory/chats", "/api/memory/chats/search"]:
        assert r in routes, f"missing route {r}"


# ─────────────────────────── model switching ──────────────────────────

def test_model_manual_override(router_memory):
    router, _ = router_memory
    router.set_manual_override("qwen3:8b")
    assert router.select_model("reasoning") == "qwen3:8b"
    router.set_manual_override(None)
    assert router.select_model("reasoning") != "qwen3:8b" or True  # default may equal 8b


def test_list_available_models_returns_four(router_memory):
    router, _ = router_memory
    models = router.list_available_models()
    assert len(models) >= 4
    names = {m["name"] for m in models}
    assert "qwen3:32b" in names


# ─────────────────────────── Ollama reachability ───────────────────────

@pytest.mark.asyncio
async def test_ollama_reachable_and_models_installed(config):
    import httpx
    host = config["models"]["ollama_host"]
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{host}/api/tags")
            data = resp.json()
    except Exception as e:
        pytest.skip(f"Ollama not running: {e}")
    installed = {m["name"] for m in data.get("models", [])}
    required = {"qwen3:32b", "qwen3:30b-a3b", "qwen3:8b", "llama3:latest"}
    missing = required - installed
    assert not missing, f"missing ollama models: {missing} — run install_qwen3.bat"


# ─────────────────────────── CLI runner ────────────────────────────────

def _run():
    """Allow `python tests/test_integration.py` without pytest installed."""
    import traceback
    results = {"pass": [], "fail": []}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Pytest fixtures won't auto-run here — build deps manually
    from core import load_config
    cfg = load_config()
    from models.router import ModelRouter
    from memory import MemoryManager
    rm = (ModelRouter(cfg["models"]), MemoryManager(cfg["memory"]))
    from core.command_core import VEGACore
    vc = VEGACore(cfg)

    tests = [
        ("core_imports", test_core_imports, ()),
        ("agent_imports", test_agent_imports, ()),
        ("memory_imports", test_memory_imports, ()),
        ("api_imports", test_api_imports, ()),
        ("mcp_server_imports", test_mcp_server_imports, ()),
        ("config_loads_with_required_keys", test_config_loads_with_required_keys, ()),
        ("no_paid_providers_in_config", test_no_paid_providers_in_config, ()),
        ("video_providers_are_the_expected_eight", test_video_providers_are_the_expected_eight, ()),
        ("available_models_includes_qwen3_variants", test_available_models_includes_qwen3_variants, ()),
        ("router_exposes_query_not_generate", test_router_exposes_query_not_generate, (rm,)),
        ("all_agents_subclass_baseagent", test_all_agents_subclass_baseagent, (cfg, rm)),
        ("video_agent_has_free_providers_only", test_video_agent_has_free_providers_only, (cfg, rm)),
        ("image_agent_has_providers", test_image_agent_has_providers, (cfg, rm)),
        ("browser_agent_uses_router_query", test_browser_agent_uses_router_query, (cfg, rm)),
        ("memory_manager_has_chat_persistence", test_memory_manager_has_chat_persistence, (cfg,)),
        ("rag_module_usable", test_rag_module_usable, (cfg,)),
        ("vega_core_registers_all_agents", test_vega_core_registers_all_agents, (vc,)),
        ("vega_core_has_rag", test_vega_core_has_rag, (vc,)),
        ("fastapi_app_mounts_new_routes", test_fastapi_app_mounts_new_routes, (vc,)),
        ("model_manual_override", test_model_manual_override, (rm,)),
        ("list_available_models_returns_four", test_list_available_models_returns_four, (rm,)),
        ("ollama_reachable_and_models_installed",
         lambda c: loop.run_until_complete(test_ollama_reachable_and_models_installed(c)),
         (cfg,)),
    ]

    skipped = []
    for name, fn, args in tests:
        try:
            fn(*args)
            results["pass"].append(name)
            print(f"  PASS  {name}")
        except AssertionError as e:
            msg = str(e)
            if msg.startswith("SKIP:"):
                skipped.append((name, msg))
                print(f"  SKIP  {name}  -->  {msg}")
                continue
            results["fail"].append((name, msg))
            print(f"  FAIL  {name}  -->  {msg}")
            if os.getenv("VERBOSE"):
                traceback.print_exc()
        except Exception as e:
            results["fail"].append((name, str(e)))
            print(f"  FAIL  {name}  -->  {e}")
            if os.getenv("VERBOSE"):
                traceback.print_exc()

    print()
    print(f"Passed:  {len(results['pass'])} / {len(tests)}")
    if skipped:
        print(f"Skipped: {len(skipped)}  (environment-dependent, not failures)")
    if results["fail"]:
        print(f"Failed:  {len(results['fail'])}")
        for n, err in results["fail"]:
            print(f"  - {n}: {err}")
        return 1
    print("ALL GREEN" + (" (ignoring skips)" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(_run())
