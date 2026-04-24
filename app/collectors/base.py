import asyncio
import logging
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class Collector(ABC):
    name: str = "collector"
    interval_s: float = 1.0

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @abstractmethod
    async def tick(self) -> None: ...

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    async def _run(self) -> None:
        try:
            await self.setup()
            while not self._stop.is_set():
                t0 = asyncio.get_event_loop().time()
                try:
                    await self.tick()
                except Exception:
                    log.exception("%s tick failed", self.name)
                dt = asyncio.get_event_loop().time() - t0
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=max(0.01, self.interval_s - dt))
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.teardown()

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name=f"collector:{self.name}")
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
