import time
from uuid import uuid4

from qdrant_edge import Point, UpdateOperation

from src.embeddings import embed
from src.shard import VECTOR_NAME, get_mutable_shard
from src.sync_worker import enqueue_point


def insert_memory(
    text: str,
    device_id: str,
    sensitivity: str = "low",
) -> str:
    if not text.strip():
        raise ValueError("memory text must not be empty")

    timestamp = time.time()
    point_id = str(uuid4())
    payload = {
        "text": text,
        "device_id": device_id,
        "timestamp": timestamp,
        "access_count": 0,
        "last_accessed": timestamp,
        "size_bytes": len(text.encode("utf-8")),
        "sensitivity": sensitivity,
        "sync_status": "local_only",
    }
    point = Point(
        id=point_id,
        vector={VECTOR_NAME: embed(text)},
        payload=payload,
    )
    get_mutable_shard(device_id).update(UpdateOperation.upsert_points([point]))
    enqueue_point(device_id, point)
    return point_id