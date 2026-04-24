import logging
from functools import lru_cache
from typing import Iterable

import numpy as np

from app.config import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers not installed. Install with `pip install -e .[kb]`"
        ) from e
    return SentenceTransformer(settings.embed_model)


def embed(texts: Iterable[str]) -> np.ndarray:
    m = _model()
    vecs = m.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
    return vecs.astype(np.float32)


def available() -> bool:
    try:
        _model()
        return True
    except Exception:
        return False
