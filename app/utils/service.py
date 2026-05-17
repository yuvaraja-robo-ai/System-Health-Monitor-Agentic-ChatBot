import re
from pathlib import Path

WINDOW_MAP: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
    "7d": 604800,
}


def parse_window(s: str | int | None, default: int = 300) -> int:
    if s is None:
        return default
    if isinstance(s, int):
        return s
    value = str(s).strip().lower()
    if value in WINDOW_MAP:
        return WINDOW_MAP[value]
    match = re.fullmatch(r"(\d+)\s*([smhd])", value)
    if not match:
        return default
    amount = int(match.group(1))
    unit = match.group(2)
    scale = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return amount * scale


def normalize(name: str | None) -> str:
    if not name:
        return ""
    base = name.strip().lower()
    for suffix in (".service", ".socket", ".timer", ".scope", ".slice", ".log", ".ndjson"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    base = Path(base).stem
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def match_score(candidate: str, other: str) -> int:
    a = normalize(candidate)
    b = normalize(other)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 80
    return len(set(a.split("-")) & set(b.split("-"))) * 10


def service_match(scope_services: list[str], candidate: str | None) -> bool:
    if not candidate:
        return False
    cand = normalize(candidate)
    if not cand:
        return False
    for svc in scope_services:
        norm = normalize(svc)
        if norm and (cand == norm or cand in norm or norm in cand):
            return True
    return False
