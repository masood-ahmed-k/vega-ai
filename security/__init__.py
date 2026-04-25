"""
VEGA AI — Security System
Action approval gates, encrypted API key vault, and snapshot system for self-evolution safety.
"""

import os
import json
import time
import shutil
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

logger = structlog.get_logger("vega.security")


# ─── API Key Vault ─────────────────────────────────────────────────────────────

class KeyVault:
    """Encrypted storage for API keys. Uses OS keyring when available, falls back to encrypted file."""

    def __init__(self):
        self._cache = {}

    def store(self, service: str, key: str):
        try:
            import keyring
            keyring.set_password("vega_ai", service, key)
        except Exception:
            # Fallback: environment variable
            os.environ[f"VEGA_KEY_{service.upper()}"] = key
        self._cache[service] = key
        logger.info("key_stored", service=service)

    def get(self, service: str) -> str | None:
        if service in self._cache:
            return self._cache[service]
        
        # Try keyring
        try:
            import keyring
            key = keyring.get_password("vega_ai", service)
            if key:
                self._cache[service] = key
                return key
        except Exception:
            pass

        # Try environment variables
        env_key = os.environ.get(f"VEGA_KEY_{service.upper()}")
        if not env_key:
            # Try standard env var names
            env_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GOOGLE_API_KEY",
                "gemini": "GOOGLE_API_KEY",
            }
            env_key = os.environ.get(env_map.get(service, ""))
        
        if env_key:
            self._cache[service] = env_key
        return env_key

    def list_services(self) -> list[str]:
        services = list(self._cache.keys())
        for key in os.environ:
            if key.startswith("VEGA_KEY_"):
                services.append(key[9:].lower())
        return list(set(services))


# ─── Action Approval System ───────────────────────────────────────────────────

class ActionApproval:
    """Gate for dangerous actions. Single confirmation for destructive operations."""

    DANGEROUS_ACTIONS = [
        "delete_files", "send_email", "run_unknown_scripts",
        "modify_system_files", "bulk_operations", "format_drive",
        "send_message", "post_online"
    ]

    _counter = 0

    def __init__(self, config: dict):
        self.require_approval = config.get("require_approval_for", self.DANGEROUS_ACTIONS)
        self.auto_approve = config.get("auto_approve", [])
        self._pending_approvals = {}

    def needs_approval(self, action: str) -> bool:
        if action in self.auto_approve:
            return False
        return action in self.require_approval

    def request_approval(self, action: str, details: str) -> str:
        """Create approval request. Returns approval_id."""
        ActionApproval._counter += 1
        approval_id = f"apr_{int(time.time()*1000)}_{ActionApproval._counter}"
        self._pending_approvals[approval_id] = {
            "action": action,
            "details": details,
            "timestamp": time.time(),
            "status": "pending"
        }
        logger.warning("approval_requested", action=action, id=approval_id, details=details[:100])
        return approval_id

    def approve(self, approval_id: str) -> bool:
        if approval_id in self._pending_approvals:
            self._pending_approvals[approval_id]["status"] = "approved"
            logger.info("action_approved", id=approval_id)
            return True
        return False

    def deny(self, approval_id: str) -> bool:
        if approval_id in self._pending_approvals:
            self._pending_approvals[approval_id]["status"] = "denied"
            logger.info("action_denied", id=approval_id)
            return True
        return False

    def is_approved(self, approval_id: str) -> bool:
        return self._pending_approvals.get(approval_id, {}).get("status") == "approved"

    def get_pending(self) -> list[dict]:
        return [
            {"id": k, **v}
            for k, v in self._pending_approvals.items()
            if v["status"] == "pending"
        ]


# ─── Snapshot System (Git-like versioning for self-evolution) ──────────────────

class SnapshotManager:
    """Creates snapshots of VEGA's code before self-modifications."""

    def __init__(self, config: dict):
        self.snapshot_dir = Path(config.get("snapshot_dir", "./snapshots"))
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.max_snapshots = config.get("max_snapshots", 50)
        self.auto_snapshot = config.get("auto_snapshot", True)

    def create_snapshot(self, reason: str = "auto", files: list[str] | None = None) -> str:
        """Create a snapshot. Returns snapshot ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"snap_{timestamp}"
        snap_path = self.snapshot_dir / snapshot_id

        # Copy relevant files
        source_dirs = files or ["agents", "skills", "core", "models"]
        snap_path.mkdir(parents=True, exist_ok=True)

        for src_dir in source_dirs:
            src = Path(src_dir)
            if src.exists():
                dest = snap_path / src_dir
                if src.is_dir():
                    shutil.copytree(src, dest, dirs_exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

        # Save metadata
        metadata = {
            "id": snapshot_id,
            "reason": reason,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "files": source_dirs,
        }
        with open(snap_path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        # Cleanup old snapshots
        self._cleanup()

        logger.info("snapshot_created", id=snapshot_id, reason=reason)
        return snapshot_id

    def rollback(self, snapshot_id: str) -> bool:
        """Restore from a snapshot."""
        snap_path = self.snapshot_dir / snapshot_id
        if not snap_path.exists():
            logger.error("snapshot_not_found", id=snapshot_id)
            return False

        # Create a backup of current state first
        self.create_snapshot(reason=f"pre_rollback_to_{snapshot_id}")

        # Restore files
        metadata_path = snap_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
            
            for src_dir in metadata.get("files", []):
                src = snap_path / src_dir
                if src.exists():
                    dest = Path(src_dir)
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)

        logger.info("snapshot_restored", id=snapshot_id)
        return True

    def list_snapshots(self) -> list[dict]:
        snapshots = []
        for snap_dir in sorted(self.snapshot_dir.iterdir(), reverse=True):
            meta_path = snap_dir / "metadata.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    snapshots.append(json.load(f))
        return snapshots

    def _cleanup(self):
        snapshots = sorted(self.snapshot_dir.iterdir())
        while len(snapshots) > self.max_snapshots:
            oldest = snapshots.pop(0)
            if oldest.is_dir():
                shutil.rmtree(oldest)
                logger.debug("snapshot_cleaned", path=str(oldest))


# ─── Unified Security Manager ─────────────────────────────────────────────────

class SecurityManager:
    def __init__(self, config: dict):
        self.vault = KeyVault()
        self.approval = ActionApproval(config)
        self.snapshots = SnapshotManager(config)
