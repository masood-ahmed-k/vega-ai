"""
VEGA AI — File Watcher
Monitors skill directory for changes and auto-reloads.
Also watches user-specified folders for file changes.
"""

import asyncio
from pathlib import Path
from typing import Callable, Optional
import structlog

logger = structlog.get_logger("vega.watcher")


class FileWatcher:
    """Watches directories for file changes."""

    def __init__(self):
        self._watches: dict[str, dict] = {}
        self._running = False

    def watch(self, directory: str, callback: Callable, pattern: str = "*.py"):
        """Register a directory to watch."""
        path = Path(directory)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        self._watches[directory] = {
            "path": path,
            "pattern": pattern,
            "callback": callback,
            "last_state": self._get_state(path, pattern),
        }
        logger.info("watching_directory", dir=directory, pattern=pattern)

    def _get_state(self, path: Path, pattern: str) -> dict[str, float]:
        """Get modification times of all matching files."""
        state = {}
        for f in path.glob(pattern):
            if f.is_file():
                state[str(f)] = f.stat().st_mtime
        return state

    async def start(self, interval: float = 2.0):
        """Start watching for changes."""
        self._running = True
        logger.info("file_watcher_started")

        while self._running:
            for name, watch in self._watches.items():
                current_state = self._get_state(watch["path"], watch["pattern"])

                # Check for new or modified files
                for filepath, mtime in current_state.items():
                    old_mtime = watch["last_state"].get(filepath)
                    if old_mtime is None:
                        logger.info("file_created", path=filepath)
                        try:
                            result = watch["callback"](filepath, "created")
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error("watcher_callback_error", error=str(e))
                    elif mtime > old_mtime:
                        logger.info("file_modified", path=filepath)
                        try:
                            result = watch["callback"](filepath, "modified")
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error("watcher_callback_error", error=str(e))

                # Check for deleted files
                for filepath in watch["last_state"]:
                    if filepath not in current_state:
                        logger.info("file_deleted", path=filepath)
                        try:
                            result = watch["callback"](filepath, "deleted")
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error("watcher_callback_error", error=str(e))

                watch["last_state"] = current_state

            await asyncio.sleep(interval)

    def stop(self):
        self._running = False
        logger.info("file_watcher_stopped")
