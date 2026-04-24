import asyncio
import concurrent.futures
import logging
import os
import socket
import subprocess
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.agent import kb
from app.analytics.anomaly import detector as anomaly_detector
from app.analytics.health import scorer
from app.analytics.leak import detector
from app.api import apps, briefing, chat, config, derived, diagnose, logs, meta, processes, prometheus, silence, sla, system, thresholds, timeline, ws
from app.collectors.app_monitor_collector import AppMonitorCollector
from app.collectors.crash_collector import CrashCollector
from app.collectors.dmesg_collector import DmesgCollector
from app.collectors.filelog_collector import FileLogCollector
from app.collectors.journald_collector import JournaldCollector
from app.collectors.jtop_collector import JtopCollector
from app.collectors.psutil_collector import ProcessCollector, PsutilCollector
from app.config import settings
from app.db import duckdb as ldb
from app.db import sqlite as sdb
from app.host import detect
from app import runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("systemhealth")

_SHUTDOWN_DEADLINE_S = 8.0


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> Response:  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

def _install_daemon_executor(loop: asyncio.AbstractEventLoop) -> None:
    """Replace asyncio default executor with one whose workers are daemon threads.
    Must set daemon=True at Thread construction — cannot set post-start."""
    import weakref
    from concurrent.futures.thread import _worker, _threads_queues

    class DaemonPool(concurrent.futures.ThreadPoolExecutor):
        def _adjust_thread_count(self):  # type: ignore[override]
            if self._idle_semaphore.acquire(timeout=0):
                return

            def weakref_cb(_, q=self._work_queue):
                q.put(None)

            num_threads = len(self._threads)
            if num_threads < self._max_workers:
                thread_name = f"{self._thread_name_prefix or self}_{num_threads}"
                t = threading.Thread(
                    name=thread_name,
                    target=_worker,
                    args=(weakref.ref(self, weakref_cb),
                          self._work_queue,
                          self._initializer,
                          self._initargs),
                    daemon=True,
                )
                t.start()
                self._threads.add(t)
                _threads_queues[t] = self._work_queue

    loop.set_default_executor(DaemonPool(max_workers=32, thread_name_prefix="sh-io"))


def _build_collectors() -> list:
    cap = detect()
    cs: list = [PsutilCollector(), ProcessCollector(), AppMonitorCollector()]
    if cap.has_jtop:
        cs.append(JtopCollector())
    if cap.has_journald:
        cs.append(JournaldCollector())
        cs.append(CrashCollector())
    if settings.log_app_dirs:
        cs.append(FileLogCollector())
    if os.getenv("SH_ENABLE_DMESG", "0").lower() not in {"0", "false", "no"}:
        cs.append(DmesgCollector())
    return cs


@asynccontextmanager
async def lifespan(app: FastAPI):
    _install_daemon_executor(asyncio.get_running_loop())

    log.info("host=%s arch=%s", detect().host, detect().arch)
    sdb.init()
    ldb._conn()
    runtime.init_pinned_apps()
    try:
        kb.build()
    except Exception:
        log.exception("kb build failed")

    collectors = _build_collectors()
    runtime.register_collectors(collectors)
    for c in collectors:
        c.start()
        log.info("started collector: %s", c.name)

    await detector.start()
    await scorer.start()
    await anomaly_detector.start()

    async def maintenance() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.to_thread(sdb.downsample)
                await asyncio.to_thread(sdb.prune)
                await asyncio.to_thread(ldb.prune)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("maintenance failed")

    maint = asyncio.create_task(maintenance(), name="maintenance")

    try:
        yield
    finally:
        log.info("shutdown: stopping tasks")

        async def _shutdown_seq() -> None:
            maint.cancel()
            try:
                await maint
            except (asyncio.CancelledError, Exception):
                pass
            await asyncio.gather(
                detector.stop(),
                scorer.stop(),
                anomaly_detector.stop(),
                *(c.stop() for c in collectors),
                return_exceptions=True,
            )
            runtime.clear_collectors()
            await asyncio.to_thread(ldb.close)

        try:
            await asyncio.wait_for(_shutdown_seq(), timeout=_SHUTDOWN_DEADLINE_S)
            log.info("shutdown: clean")
        except asyncio.TimeoutError:
            log.warning("shutdown: timeout after %.1fs — cancelling remaining tasks", _SHUTDOWN_DEADLINE_S)
            for t in asyncio.all_tasks():
                if t is not asyncio.current_task():
                    t.cancel()


app = FastAPI(title="SystemHealth", version="0.1.0", lifespan=lifespan)

_ALLOWED_ORIGINS = [
    "http://localhost:9090",
    "http://127.0.0.1:9090",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(meta.router)
app.include_router(config.router)
app.include_router(system.router)
app.include_router(processes.router)
app.include_router(logs.router)
app.include_router(apps.router)
app.include_router(briefing.router)
app.include_router(derived.router)
app.include_router(diagnose.router)
app.include_router(prometheus.router)
app.include_router(thresholds.router)
app.include_router(sla.router)
app.include_router(timeline.router)
app.include_router(silence.router)
app.include_router(chat.router)
app.include_router(ws.router)


@app.get("/", include_in_schema=False)
def _root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard.html")


app.mount("/", NoCacheStaticFiles(directory=str(settings.static_dir), html=True), name="static")


def _port_owner(host: str, port: int) -> str | None:
    try:
        import psutil
    except Exception:
        psutil = None

    if psutil is not None:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if not conn.laddr:
                    continue
                if conn.laddr.port != port:
                    continue
                if host not in ("0.0.0.0", "::") and conn.laddr.ip not in ("0.0.0.0", "::", host):
                    continue
                pid = conn.pid
                if not pid:
                    return f"Port {port} is already in use."
                try:
                    proc = psutil.Process(pid)
                    cmd = " ".join(proc.cmdline()) or proc.name()
                except Exception:
                    cmd = f"pid {pid}"
                return (
                    f"Port {port} is already in use by PID {pid}: {cmd}\n"
                    f"Stop it with: kill -TERM {pid}"
                )
        except Exception:
            pass

    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        lines = [line for line in out.stdout.splitlines() if line.strip()]
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 2 and parts[1].isdigit():
                pid = int(parts[1])
                cmd = parts[0]
                return (
                    f"Port {port} is already in use by PID {pid}: {cmd}\n"
                    f"Stop it with: kill -TERM {pid}"
                )
    except Exception:
        pass

    try:
        out = subprocess.run(
            ["ss", "-ltnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        for line in out.stdout.splitlines():
            if "pid=" not in line:
                continue
            pid_text = line.split("pid=", 1)[1].split(",", 1)[0].rstrip(")")
            cmd_text = line.split('users:(("', 1)[1].split('"', 1)[0] if 'users:(("' in line else "process"
            if pid_text.isdigit():
                pid = int(pid_text)
                return (
                    f"Port {port} is already in use by PID {pid}: {cmd_text}\n"
                    f"Stop it with: kill -TERM {pid}"
                )
    except Exception:
        pass

    return None


def _port_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    bind_host = "::" if host == "0.0.0.0" and family == socket.AF_INET6 else host
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
    except OSError:
        return False
    return True


def main() -> int:
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "9090"))
    reload = os.getenv("RELOAD", "1").lower() not in {"0", "false", "no"}

    if not _port_available(host, port):
        msg = _port_owner(host, port) or (
            f"Port {port} is already in use.\n"
            f"Find the owner with: lsof -nP -iTCP:{port}"
        )
        print(msg, file=sys.stderr)
        return 1

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
