"""
VEGA AI — Task Scheduler
Cron-style recurring tasks, reminders, and scheduled automations.
"""

import asyncio
from datetime import datetime
from typing import Callable, Optional
import structlog

from core.event_bus import event_bus, Event

logger = structlog.get_logger("vega.scheduler")


class ScheduledTask:
    def __init__(self, name: str, callback: Callable, interval_seconds: int = 0,
                 cron: str = "", run_at: datetime | None = None, data: dict | None = None):
        self.name = name
        self.callback = callback
        self.interval_seconds = interval_seconds
        self.cron = cron
        self.run_at = run_at
        self.data = data or {}
        self.last_run: float = 0
        self.run_count: int = 0
        self.enabled: bool = True


class Scheduler:
    """Simple async task scheduler for VEGA."""

    def __init__(self, config: dict):
        self.config = config
        self.tasks: dict[str, ScheduledTask] = {}
        self._running = False

    def add_task(self, name: str, callback: Callable, interval_seconds: int = 0,
                 cron: str = "", run_at: datetime | None = None, data: dict | None = None):
        task = ScheduledTask(name=name, callback=callback, interval_seconds=interval_seconds,
                             cron=cron, run_at=run_at, data=data)
        self.tasks[name] = task
        logger.info("task_scheduled", name=name, interval=interval_seconds)

    def remove_task(self, name: str):
        if name in self.tasks:
            del self.tasks[name]
            logger.info("task_removed", name=name)

    def list_tasks(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "interval": t.interval_seconds,
                "run_count": t.run_count,
                "enabled": t.enabled,
                "last_run": t.last_run,
            }
            for t in self.tasks.values()
        ]

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        logger.info("scheduler_started")
        
        while self._running:
            now = datetime.now()
            
            for task in list(self.tasks.values()):
                if not task.enabled:
                    continue
                
                should_run = False

                # One-time task
                if task.run_at and now >= task.run_at and task.run_count == 0:
                    should_run = True

                # Interval-based task
                elif task.interval_seconds > 0:
                    import time
                    if time.time() - task.last_run >= task.interval_seconds:
                        should_run = True

                if should_run:
                    try:
                        import time
                        result = task.callback(task.data)
                        if asyncio.iscoroutine(result):
                            await result
                        task.last_run = time.time()
                        task.run_count += 1
                        
                        await event_bus.publish(Event(
                            type="scheduler.task_executed",
                            data={"name": task.name, "run_count": task.run_count},
                            source="scheduler"
                        ))
                    except Exception as e:
                        logger.error("scheduled_task_failed", name=task.name, error=str(e))

                    # Remove one-time tasks after execution
                    if task.run_at and task.run_count > 0:
                        task.enabled = False

            await asyncio.sleep(1)

    def stop(self):
        self._running = False
        logger.info("scheduler_stopped")
