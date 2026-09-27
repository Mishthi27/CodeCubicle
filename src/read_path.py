import logging
import time

from qdrant_edge import Query, QueryRequest, ScrollRequest

from src.embeddings import embed
from src.shard import VECTOR_NAME, get_immutable_shard, get_mutable_shard


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
        merged_by_id = {}
        for shard in (get_mutable_shard(device_id), get_immutable_shard(device_id)):
            matches = shard.query(
                QueryRequest(
                    query=Query.Nearest(vector, using=VECTOR_NAME),
                    limit=top_k,
                    with_payload=True,
                    with_vector=False,
                )
            )
            for match in matches:
                result = {
                    "id": str(match.id),
                    "score": float(match.score),
                    "payload": dict(match.payload or {}),
                }
                existing = merged_by_id.get(result["id"])
                if existing is None or result["score"] > existing["score"]:
                    merged_by_id[result["id"]] = result

        return sorted(
            merged_by_id.values(),
            key=lambda result: result["score"],
            reverse=True,
        )[:top_k]
    finally:
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info("search latency_ms=%.2f", latency_ms)


def list_memories(device_id: str | None = None, limit: int = 100) -> list[dict]:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    merged_by_id = {}
    for shard in (get_mutable_shard(device_id), get_immutable_shard(device_id)):
        records, _ = shard.scroll(
            ScrollRequest(limit=limit, with_payload=True, with_vector=False)
        )
        for record in records:
            result = {
                "id": str(record.id),
                "payload": dict(record.payload or {}),
            }
            existing = merged_by_id.get(result["id"])
            if existing is None or result["payload"].get("timestamp", 0) > existing[
                "payload"
            ].get("timestamp", 0):
                merged_by_id[result["id"]] = result

    return sorted(
        merged_by_id.values(),
        key=lambda result: result["payload"].get("timestamp", 0),
        reverse=True,
    )[:limit]


def shard_counts(device_id: str) -> dict[str, int]:
    counts = {}
    for shard_name, shard in (
        ("mutable", get_mutable_shard(device_id)),
        ("immutable", get_immutable_shard(device_id)),
    ):
        count = 0
        offset = None
        while True:
            records, offset = shard.scroll(
                ScrollRequest(
                    offset=offset,
                    limit=512,
                    with_payload=False,
                    with_vector=False,
                )
            )
            count += len(records)
            if offset is None or not records:
                break
        counts[shard_name] = count
    return counts