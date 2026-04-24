import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from app.agent import embed
from app.config import settings

log = logging.getLogger(__name__)

_INDEX = None
_META: list[dict[str, Any]] = []
_HASH: str | None = None


def _kb_hash(kb_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(kb_dir.glob("*.md")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _parse_doc(path: Path) -> dict[str, Any]:
    text = path.read_text()
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    title = title_match.group(1).strip() if title_match else path.stem
    tags = []
    tags_match = re.search(r"^tags:\s*(.+)$", text, re.M | re.I)
    if tags_match:
        tags = [t.strip() for t in tags_match.group(1).split(",")]
    steps: list[str] = []
    steps_block = re.search(r"^##\s*Steps\s*$(.*?)(?=^##|\Z)", text, re.M | re.S | re.I)
    if steps_block:
        for line in steps_block.group(1).splitlines():
            s = line.strip()
            if re.match(r"^(\d+\.|-|\*)\s+", s):
                steps.append(re.sub(r"^(\d+\.|-|\*)\s+", "", s))
    return {
        "id": path.stem,
        "title": title,
        "md_path": str(path),
        "tags": tags,
        "steps": steps,
        "text": text,
    }


def build(force: bool = False) -> None:
    global _INDEX, _META, _HASH
    kb_dir = settings.kb_path
    if not kb_dir.exists():
        return
    cur_hash = _kb_hash(kb_dir)
    if not force and _HASH == cur_hash and _INDEX is not None:
        return
    docs = [_parse_doc(p) for p in sorted(kb_dir.glob("*.md"))]
    if not docs:
        _INDEX, _META, _HASH = None, [], cur_hash
        return
    try:
        import faiss  # type: ignore
    except ImportError:
        log.warning("faiss not installed — KB disabled")
        _INDEX, _META, _HASH = None, [], cur_hash
        return
    if not embed.available():
        log.warning("embedding model unavailable — KB disabled")
        _INDEX, _META, _HASH = None, [], cur_hash
        return
    texts = [f"{d['title']}\n{d['text']}" for d in docs]
    vecs = embed.embed(texts)
    dim = vecs.shape[1]
    idx = faiss.IndexFlatIP(dim)
    idx.add(vecs)
    _INDEX = idx
    _META = [{k: v for k, v in d.items() if k != "text"} for d in docs]
    _HASH = cur_hash
    (kb_dir / "meta.json").write_text(json.dumps(_META, indent=2))
    faiss.write_index(idx, str(kb_dir / "faiss.index"))


def query(text: str, k: int = 5) -> list[dict[str, Any]]:
    if _INDEX is None:
        return []
    vec = embed.embed([text])
    scores, ids = _INDEX.search(vec, k)
    out: list[dict[str, Any]] = []
    for s, i in zip(scores[0].tolist(), ids[0].tolist()):
        if i < 0 or i >= len(_META):
            continue
        m = dict(_META[i])
        m["score"] = float(s)
        out.append(m)
    return out
