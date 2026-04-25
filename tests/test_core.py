"""
VEGA AI — Test Suite
Unit and integration tests for core modules.

Run with: python -m pytest tests/ -v
"""

import asyncio
import json
import tempfile
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Test Configuration ───────────────────────────────────────────────────────

class TestConfig:
    """Test configuration loader."""

    def test_load_config(self):
        from core import load_config, reload_config
        reload_config()
        config = load_config()
        assert isinstance(config, dict)
        assert "models" in config
        assert "memory" in config
        assert "security" in config

    def test_get_nested_config(self):
        from core import get, reload_config
        reload_config()
        result = get("models.default_cloud")
        assert result is not None

    def test_get_missing_key(self):
        from core import get, reload_config
        reload_config()
        result = get("nonexistent.key", "default")
        assert result == "default"


# ─── Test Event Bus ────────────────────────────────────────────────────────────

class TestEventBus:
    """Test event bus publish/subscribe."""

    def test_subscribe_and_publish(self):
        from core.event_bus import EventBus, Event
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        event = Event(type="test.event", data={"key": "value"})
        asyncio.get_event_loop().run_until_complete(bus.publish(event))
        assert len(received) == 1
        assert received[0].data["key"] == "value"

    def test_wildcard_handler(self):
        from core.event_bus import EventBus, Event
        bus = EventBus()
        received = []

        bus.subscribe("*", lambda e: received.append(e))
        asyncio.get_event_loop().run_until_complete(
            bus.publish(Event(type="any.event", data="test"))
        )
        assert len(received) == 1

    def test_history(self):
        from core.event_bus import EventBus, Event
        bus = EventBus()
        asyncio.get_event_loop().run_until_complete(
            bus.publish(Event(type="test", data="1"))
        )
        asyncio.get_event_loop().run_until_complete(
            bus.publish(Event(type="test", data="2"))
        )
        history = bus.get_history("test")
        assert len(history) == 2


# ─── Test Memory System ───────────────────────────────────────────────────────

class TestMemory:
    """Test memory subsystems."""

    def test_working_memory(self):
        from memory import WorkingMemory
        wm = WorkingMemory(max_size=5)
        wm.add("hello", role="user")
        wm.add("world", role="assistant")
        context = wm.get_context()
        assert len(context) == 2
        assert context[0]["content"] == "hello"

    def test_working_memory_overflow(self):
        from memory import WorkingMemory
        wm = WorkingMemory(max_size=3)
        for i in range(10):
            wm.add(f"message {i}")
        assert len(wm.entries) == 3
        assert wm.entries[0].content == "message 7"

    def test_working_memory_search(self):
        from memory import WorkingMemory
        wm = WorkingMemory()
        wm.add("Python programming")
        wm.add("JavaScript tutorial")
        results = wm.search("python")
        assert len(results) == 1

    def test_procedural_memory(self):
        from memory import ProceduralMemory
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            pm = ProceduralMemory(db_path=db_path)
            pm.set_preference("theme", "dark")
            assert pm.get_preference("theme") == "dark"
            assert pm.get_preference("missing", "default") == "default"

            pm.record_task("test task", "planner", "done", True, 1.5)
            tasks = pm.get_recent_tasks(limit=5)
            assert len(tasks) == 1
            assert tasks[0]["task"] == "test task"
        finally:
            os.unlink(db_path)

    def test_procedural_workflow(self):
        from memory import ProceduralMemory
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            pm = ProceduralMemory(db_path=db_path)
            pm.save_workflow("deploy", ["build", "test", "push", "verify"])
            steps = pm.get_workflow("deploy")
            assert steps == ["build", "test", "push", "verify"]
            assert pm.get_workflow("nonexistent") is None
        finally:
            os.unlink(db_path)

    def test_knowledge_graph(self):
        from memory import KnowledgeGraph
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            kg_path = f.name
        try:
            kg = KnowledgeGraph(persist_path=kg_path)
            kg.add_entity("Hunter", "person", {"role": "developer"})
            kg.add_entity("VEGA", "project", {"type": "AI"})
            kg.add_relation("Hunter", "VEGA", "created")

            result = kg.query_entity("Hunter")
            assert result is not None
            assert result["entity"] == "Hunter"
            assert len(result["relations"]) >= 1

            search = kg.search("hunter")
            assert "Hunter" in search
        finally:
            os.unlink(kg_path)


# ─── Test Security ─────────────────────────────────────────────────────────────

class TestSecurity:
    """Test security subsystems."""

    def test_action_approval(self):
        from security import ActionApproval
        approval = ActionApproval({"require_approval_for": ["delete_files"]})
        assert approval.needs_approval("delete_files") == True
        assert approval.needs_approval("read_file") == False

        approval_id = approval.request_approval("delete_files", "deleting temp")
        assert not approval.is_approved(approval_id)
        approval.approve(approval_id)
        assert approval.is_approved(approval_id)

    def test_approval_deny(self):
        from security import ActionApproval
        approval = ActionApproval({"require_approval_for": ["send_email"]})
        approval_id = approval.request_approval("send_email", "test")
        approval.deny(approval_id)
        assert not approval.is_approved(approval_id)

    def test_pending_approvals(self):
        from security import ActionApproval
        approval = ActionApproval({"require_approval_for": ["delete_files"]})
        approval.request_approval("delete_files", "test1")
        approval.request_approval("delete_files", "test2")
        pending = approval.get_pending()
        assert len(pending) == 2

    def test_snapshot_manager(self):
        from security import SnapshotManager
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SnapshotManager({"snapshot_dir": tmpdir, "max_snapshots": 5})
            snap_id = sm.create_snapshot(reason="test")
            assert snap_id.startswith("snap_")

            snapshots = sm.list_snapshots()
            assert len(snapshots) >= 1
            assert snapshots[0]["reason"] == "test"

    def test_key_vault_env(self):
        from security import KeyVault
        vault = KeyVault()
        os.environ["VEGA_KEY_TESTSERVICE"] = "test_key_123"
        key = vault.get("testservice")
        assert key == "test_key_123"
        del os.environ["VEGA_KEY_TESTSERVICE"]


# ─── Test Model Router ─────────────────────────────────────────────────────────

class TestModelRouter:
    """Test model selection and routing."""

    def test_model_selection(self):
        from models.router import ModelRouter
        router = ModelRouter({"routing": {"coding": "codellama"}, "fallback_chain": ["gpt-4o"]})
        router.stats = {}  # Clear persistent learned stats so config routing applies
        assert router.select_model("coding") == "codellama"

    def test_force_model(self):
        from models.router import ModelRouter
        router = ModelRouter({})
        assert router.select_model("coding", force_model="gpt-4o") == "gpt-4o"

    def test_stats_tracking(self):
        from models.router import ModelRouter
        router = ModelRouter({"fallback_chain": ["gpt-4o"]})
        router.stats = {}  # Reset state
        router._record_stats("coding", "codellama", 1.5, True, 0.8)
        router._record_stats("coding", "codellama", 2.0, True, 0.9)
        stats = router.get_stats_summary()
        assert "coding" in stats
        assert stats["coding"]["codellama"]["calls"] == 2

    def test_feedback(self):
        from models.router import ModelRouter
        router = ModelRouter({})
        router._record_stats("test", "model_a", 1.0, True)
        router.record_feedback("test", "model_a", 0.95)
        assert router.stats["test"]["model_a"].score > 0.5


# ─── Test Skill System ────────────────────────────────────────────────────────

class TestSkillSystem:
    """Test skill loading and chaining."""

    def test_discover_skills(self):
        from skills import SkillLoader
        loader = SkillLoader(skill_dir="./skills/builtins")
        skills = loader.discover()
        assert len(skills) >= 1

    def test_skill_chain_placeholder(self):
        from skills import SkillChain
        from agents import AgentRegistry
        registry = AgentRegistry()
        chain = SkillChain(registry)
        assert chain is not None


# ─── Test Scheduler ────────────────────────────────────────────────────────────

class TestScheduler:
    """Test task scheduling."""

    def test_add_task(self):
        from scheduler import Scheduler
        sched = Scheduler({})
        sched.add_task("test_task", lambda data: None, interval_seconds=60)
        tasks = sched.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "test_task"

    def test_remove_task(self):
        from scheduler import Scheduler
        sched = Scheduler({})
        sched.add_task("temp", lambda data: None, interval_seconds=60)
        sched.remove_task("temp")
        assert len(sched.list_tasks()) == 0


# ─── Run Tests ─────────────────────────────────────────────────────────────────

def run_all_tests():
    """Simple test runner (no pytest dependency needed)."""
    test_classes = [
        TestConfig, TestEventBus, TestMemory, TestSecurity,
        TestModelRouter, TestSkillSystem, TestScheduler
    ]
    
    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        print(f"\n  Testing {cls.__name__}...")
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"    PASS {method_name}")
                    passed += 1
                except Exception as e:
                    print(f"    FAIL {method_name}: {e}")
                    failed += 1
                    errors.append((f"{cls.__name__}.{method_name}", str(e)))

    print(f"\n  Results: {passed} passed, {failed} failed")
    if errors:
        print("\n  Failures:")
        for name, err in errors:
            print(f"    {name}: {err}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
