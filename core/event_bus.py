"""
VEGA AI — Event Bus
Publish/subscribe system for inter-agent and inter-module communication.
"""

import asyncio
import time
from typing import Any, Callable, Coroutine
from dataclasses import dataclass, field
from collections import defaultdict
import structlog

logger = structlog.get_logger("vega.eventbus")


@dataclass
class Event:
    type: str
    data: Any = None
    source: str = "system"
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: f"evt_{int(time.time()*1000)}")


class EventBus:
    """Central event bus for VEGA. Supports sync and async handlers."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 500

    def subscribe(self, event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)
        logger.debug("handler_subscribed", event_type=event_type, handler=handler.__name__)

    def unsubscribe(self, event_type: str, handler: Callable):
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event: Event):
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.info("event_published", event_type=event.type, source=event.source)

        # Notify all handlers for this event type + wildcard handlers
        handlers = self._handlers.get(event.type, []) + self._handlers.get("*", [])
        
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("handler_error", event_type=event.type, handler=handler.__name__, error=str(e))

    def publish_sync(self, event: Event):
        """Synchronous publish for non-async contexts."""
        self._history.append(event)
        handlers = self._handlers.get(event.type, []) + self._handlers.get("*", [])
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(result)
                    else:
                        loop.run_until_complete(result)
            except Exception:
                pass

    def get_history(self, event_type: str | None = None, limit: int = 50) -> list[Event]:
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]


# Global singleton
event_bus = EventBus()
