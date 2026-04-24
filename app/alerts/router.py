"""Outbound alert routing — webhook delivery with dedup/cooldown.

Configure via env:
    SH_ALERT_WEBHOOK_URL=https://hooks.slack.com/...
    SH_ALERT_COOLDOWN_S=300   (default: 5 min)

Payload sent to webhook:
    {
        "ts": 1714000000,
        "severity": "err",
        "source": "anomaly",
        "message": "cpu.total z=4.2",
        "host": "jetson-nano",
        "context": {...}
    }
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.host import detect

log = logging.getLogger(__name__)


class AlertRouter:
    def __init__(self) -> None:
        self._cache: dict[str, float] = {}
        self.silence_until: float = 0.0

    def _dedup_key(self, source: str, message: str) -> str:
        return f"{source}:{message[:80]}"

    def _silenced(self) -> bool:
        return time.time() < self.silence_until

    def _allowed(self, key: str) -> bool:
        if self._silenced():
            return False
        now = time.time()
        last = self._cache.get(key, 0.0)
        if now - last < settings.alert_cooldown_s:
            return False
        self._cache[key] = now
        return True

    async def send(
        self,
        severity: str,
        source: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        key = self._dedup_key(source, message)
        if not self._allowed(key):
            return

        if not settings.alert_webhook_url:
            return

        payload = {
            "ts": int(time.time()),
            "severity": severity,
            "source": source,
            "message": message,
            "host": detect().host or "unknown",
            "context": context or {},
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(settings.alert_webhook_url, json=payload)
                if resp.status_code >= 400:
                    log.warning("alert webhook %s: HTTP %s", settings.alert_webhook_url, resp.status_code)
        except Exception:
            log.exception("alert webhook failed")

    def send_sync(
        self,
        severity: str,
        source: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Fire-and-forget from sync context (schedules coroutine on running loop)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.send(severity, source, message, context))
        except Exception:
            pass


alert_router = AlertRouter()
