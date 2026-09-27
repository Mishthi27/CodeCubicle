import time
import os
from uuid import uuid4

from qdrant_edge import Point, Query, QueryRequest, UpdateOperation

from src.embeddings import embed
from src.policy_model import decide as decide_model
from src.policy_rules import decide as decide_rules
from src.shard import VECTOR_NAME, get_immutable_shard, get_mutable_shard
from src.sync_worker import enqueue_point


def insert_memory(
    text: str,
    device_id: str,
    sensitivity: str = "low",
    *,
    point_id: str | None = None,
    timestamp: float | None = None,
) -> str:
    if not text.strip():
        raise ValueError("memory text must not be empty")

    timestamp = time.time() if timestamp is None else float(timestamp)
    point_id = point_id or str(uuid4())
    vector = embed(text)
    known_matches = get_immutable_shard(device_id).query(
        QueryRequest(
            query=Query.Nearest(vector, using=VECTOR_NAME),
            limit=1,
            with_payload=False,
            with_vector=False,
        )
    )
    novelty_score = float(known_matches[0].score) if known_matches else 0.0
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
    policy_name = os.getenv("SYNC_POLICY", "model").strip().lower()
    if policy_name == "rules":
        decision, confidence, reason = decide_rules(payload, novelty_score)
    elif policy_name == "model":
        decision, confidence, reason = decide_model(payload, novelty_score)
    else:
        raise ValueError("SYNC_POLICY must be 'model' or 'rules'")
    payload.update(
        {
            "sync_decision": decision,
            "sync_confidence": confidence,
            "sync_reason": reason,
            "novelty_score": novelty_score,
        }
    )
    point = Point(
        id=point_id,
        vector={VECTOR_NAME: vector},
        payload=payload,
    )
    get_mutable_shard(device_id).update(UpdateOperation.upsert_points([point]))
    if decision == "sync":
        enqueue_point(device_id, point)
    return point_id