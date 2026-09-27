import logging
import time

from qdrant_edge import Query, QueryRequest

from src.embeddings import embed
from src.shard import VECTOR_NAME, get_mutable_shard


logger = logging.getLogger(__name__)


def search(
    query: str,
    top_k: int = 5,
    device_id: str | None = None,
) -> list[dict]:
    started = time.perf_counter()
    try:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        vector = embed(query)
        matches = get_mutable_shard(device_id).query(
            QueryRequest(
                query=Query.Nearest(vector, using=VECTOR_NAME),
                limit=top_k,
                with_payload=True,
                with_vector=False,
            )
        )
        return [
            {
                "id": str(match.id),
                "score": float(match.score),
                "payload": dict(match.payload or {}),
            }
            for match in matches
        ]
    finally:
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info("search latency_ms=%.2f", latency_ms)