"""Keyword routing config loader — edit keywords.json to tune query matching."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads((Path(__file__).parent / "keywords.json").read_text())


def metric_keywords(name: str) -> list[str]:
    return _load()["metrics"].get(name, {}).get("keywords", [])


def metric_exclude(name: str) -> list[str]:
    return _load()["metrics"].get(name, {}).get("exclude", [])


def metric_names() -> list[str]:
    return list(_load()["metrics"].keys())


def process_metric_keywords() -> list[str]:
    return _load()["process_query"]["metric_keywords"]


def process_scope_keywords() -> list[str]:
    return _load()["process_query"]["system_scope"]


def reasoning_keywords() -> list[str]:
    return _load()["reasoning"]
