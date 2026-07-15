import hashlib
from functools import lru_cache

from fastembed import TextEmbedding

from .config import settings


@lru_cache(maxsize=1)
def model() -> TextEmbedding:
    settings.embedding_cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=settings.embedding_model, cache_dir=str(settings.embedding_cache_dir))


def semantic_embed(text: str) -> list[float]:
    return list(next(model().embed([text])))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
