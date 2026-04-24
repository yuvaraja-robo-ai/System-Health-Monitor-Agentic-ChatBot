import os
import platform
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Capabilities:
    host: str
    arch: str
    has_jtop: bool
    has_journald: bool
    has_fan: bool
    has_power_mode: bool
    jetson_model: str | None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(errors="ignore").strip()
    except OSError:
        return None


@lru_cache(maxsize=1)
def detect() -> Capabilities:
    arch = platform.machine()
    jetson_model = None
    is_jetson = False

    tegra = _read("/etc/nv_tegra_release")
    if tegra:
        is_jetson = True
    dtm = _read("/proc/device-tree/model")
    if dtm and ("NVIDIA" in dtm or "Jetson" in dtm or "Orin" in dtm):
        is_jetson = True
        jetson_model = dtm.replace("\x00", "").strip()

    has_jtop = False
    if is_jetson:
        try:
            import jtop  # noqa: F401
            has_jtop = True
        except ImportError:
            has_jtop = False

    has_journald = False
    try:
        from systemd import journal  # noqa: F401
        has_journald = True
    except ImportError:
        has_journald = False

    has_fan = Path("/sys/class/hwmon").exists() and any(
        "fan" in (p.name + (_read(str(p / "name")) or "")).lower()
        for p in Path("/sys/class/hwmon").glob("hwmon*")
        if p.is_dir()
    )

    has_power_mode = is_jetson and Path("/etc/nvpmodel.conf").exists()

    return Capabilities(
        host="jetson" if is_jetson else "ubuntu",
        arch=arch,
        has_jtop=has_jtop,
        has_journald=has_journald,
        has_fan=has_fan,
        has_power_mode=has_power_mode,
        jetson_model=jetson_model,
    )


def uptime_seconds() -> float:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except OSError:
        return 0.0


def kernel() -> str:
    return platform.release()


def power_mode() -> str | None:
    cap = detect()
    if not cap.has_power_mode:
        return None
    cur = _read("/etc/nvpmodel.conf")
    try:
        import subprocess
        out = subprocess.check_output(["nvpmodel", "-q"], text=True, timeout=2)
        for line in out.splitlines():
            if "NV Power Mode" in line:
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown" if cur else None
