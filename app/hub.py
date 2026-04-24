import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)


class Hub:
    def __init__(self, buffer: int = 128) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq: dict[str, int] = defaultdict(int)
        self._last: dict[str, dict[str, Any]] = {}
        self._buffer = buffer
        self._heartbeat: dict[str, float] = {}

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._buffer)
        self._subs[topic].add(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        self._subs[topic].discard(q)

    def publish(self, topic: str, data: Any) -> None:
        self._seq[topic] += 1
        envelope = {
            "topic": topic,
            "ts_ms": int(time.time() * 1000),
            "seq": self._seq[topic],
            "data": data,
        }
        self._last[topic] = envelope
        self._heartbeat[topic] = time.time()
        for q in list(self._subs[topic]):
            if q.full():
                try:
                    q.get_nowait()
                    log.debug("hub: dropped oldest message on topic=%s (queue full)", topic)
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(envelope)
            except asyncio.QueueFull:
                log.warning("hub: failed to enqueue on topic=%s after drop", topic)

    def latest(self, topic: str) -> dict[str, Any] | None:
        return self._last.get(topic)

    def heartbeats(self) -> dict[str, float]:
        return dict(self._heartbeat)


hub = Hub()
