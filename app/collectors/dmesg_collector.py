import asyncio
import logging
import re
import subprocess
import time
from typing import Any

from app.collectors.base import Collector
from app.db import duckdb as ldb

log = logging.getLogger(__name__)


class DmesgCollector(Collector):
    """Ingest kernel log (dmesg) into DuckDB for analysis.

    Captures thermal throttling, OOM kills, GPU errors, power events, etc.
    Parses dmesg output into structured logs.
    """

    name = "dmesg"
    interval_s = 30.0  # check every 30 seconds

    def __init__(self) -> None:
        super().__init__()
        self.last_line = 0  # Track last processed line number

    async def tick(self) -> None:
        snap = await asyncio.to_thread(self._snapshot)
        if snap:
            await asyncio.to_thread(ldb.write_logs, snap)

    def _snapshot(self) -> list[tuple[int, str, str, str]] | None:
        """Read dmesg since last check, parse into log tuples."""
        try:
            result = subprocess.run(
                ["dmesg", "-T", "-L"],  # -T = human time, -L = force color off
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

        rows: list[tuple[int, str, str, str]] = []
        now = int(time.time())

        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            parsed = self._parse_dmesg_line(line)
            if parsed:
                ts, severity, message = parsed
                # Service = kernel subsystem (GPU, thermal, memory, etc.)
                service = self._extract_service(message)
                rows.append((ts, service, severity, message))

        return rows if rows else None

    @staticmethod
    def _parse_dmesg_line(line: str) -> tuple[int, str, str] | None:
        """Parse dmesg line format:

        Examples:
            [Tue Apr 23 12:34:56 2026] nouveau: error message
            [  123.456789] kernel: thermal throttle
        """
        # Try human-readable timestamp format (dmesg -T)
        match = re.match(
            r"\[(.*?)\]\s+(.+)",
            line,
        )
        if not match:
            return None

        ts_str, msg = match.groups()
        severity = DmesgCollector._infer_severity(msg)

        # Try to parse timestamp as epoch
        ts = None
        try:
            from datetime import datetime
            # Format: "Tue Apr 23 12:34:56 2026" or "  123.456789"
            if ":" in ts_str and len(ts_str) > 10:
                # Parse human timestamp
                dt = datetime.strptime(ts_str, "%a %b %d %H:%M:%S %Y")
                ts = int(dt.timestamp())
            else:
                # Fallback: use current time
                ts = int(time.time())
        except (ValueError, Exception):
            ts = int(time.time())

        return ts, severity, msg

    @staticmethod
    def _infer_severity(message: str) -> str:
        """Infer severity from dmesg message content."""
        msg_upper = message.upper()

        # Critical severity
        if any(x in msg_upper for x in ["FATAL", "PANIC", "BUG", "OOPS", "SEGFAULT", "SIGSEGV"]):
            return "CRIT"

        # High severity (critical alerts)
        if any(
            x in msg_upper
            for x in [
                "OUT OF MEMORY",
                "KILL PROCESS",
                "KILLED PROCESS",
                "OOM KILLER",
                "MEMORY PRESSURE",
                "GPU RAIL OFF",
                "MODULE RESTART",
                "REBOOT",
                "BROWNOUT",
            ]
        ):
            return "ERR"

        # Medium severity (warnings/throttling)
        if any(
            x in msg_upper
            for x in [
                "THROTTLE",
                "THERMAL",
                "OVERHEAT",
                "UNDER VOLTAGE",
                "VOLTAGE DROP",
                "WARNING",
                "WARN",
                "ERROR",
            ]
        ):
            return "WARN"

        # Default to info
        return "INFO"

    @staticmethod
    def _extract_service(message: str) -> str:
        """Extract kernel subsystem from message.

        Examples:
            "nouveau: ..." → "gpu"
            "tegra-soctherm: THROTTLE" → "thermal"
            "Out of memory: Kill" → "memory"
        """
        msg = message.lower()

        # GPU/driver subsystems
        if any(x in msg for x in ["nouveau", "gpu", "cuda", "nvidia"]):
            return "kernel-gpu"

        # Thermal subsystem
        if any(x in msg for x in ["thermal", "soctherm", "throttle", "overheat", "temperature"]):
            return "kernel-thermal"

        # Memory subsystem
        if any(x in msg for x in ["memory", "oom", "killed process", "out of memory"]):
            return "kernel-memory"

        # Power subsystem
        if any(x in msg for x in ["power", "pmic", "voltage", "brownout", "rail"]):
            return "kernel-power"

        # IO/filesystem
        if any(x in msg for x in ["io", "disk", "filesystem", "ext4", "mount"]):
            return "kernel-io"

        # Network
        if any(x in msg for x in ["network", "eth", "usb", "link"]):
            return "kernel-net"

        # USB
        if any(x in msg for x in ["usb", "device"]):
            return "kernel-usb"

        # Default: generic kernel
        return "kernel"
