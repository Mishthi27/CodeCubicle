import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SYNC_POLICY"] = "model"
os.environ["OFFLINE"] = "1"

from qdrant_client import QdrantClient
from qdrant_edge import ScrollRequest

from src.conflict import read_conflicts
from src.policy_model import METRICS_PATH, decide as decide_model, train_model
from src.policy_rules import decide as decide_rules
from src.read_path import shard_counts
from src.shard import close_all_shards, get_mutable_shard
from src.sync_worker import queued_count, read_sync_log, run_sync_once
from src.write_path import insert_memory


def verify_model_metrics() -> dict:
    metrics = train_model()
    saved_metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    assert metrics == saved_metrics
    assert metrics["held_out_samples"] > 0
    assert metrics["accuracy"] >= 0.90
    assert metrics["sync_precision"] >= 0.90
    assert metrics["sync_recall"] >= 0.90
    print(
        "HELD_OUT_METRICS "
        f"accuracy={metrics['accuracy']:.4f} "
        f"sync_precision={metrics['sync_precision']:.4f} "
        f"sync_recall={metrics['sync_recall']:.4f} "
        f"f1={metrics['sync_f1']:.4f} "
        f"train={metrics['training_samples']} test={metrics['held_out_samples']}"
    )
    print(f"METRICS_SAVED={METRICS_PATH}")
    return metrics


def verify_policy_switch() -> None:
    payload = {
        "timestamp": time.time(),
        "access_count": 0,
        "size_bytes": 128,
        "sensitivity": "low",
    }
    model_decision = decide_model(payload, 0.1)
    rules_decision = decide_rules(payload, 0.1)
    assert model_decision[0] == rules_decision[0] == "sync"
    assert "trained logistic regression" in model_decision[2]
    print(
        f"POLICY_INTERFACES=PASS model={model_decision[0]} "
        f"rules={rules_decision[0]} model_confidence={model_decision[1]:.4f}"
    )

    suffix = uuid.uuid4().hex[:8]
    os.environ["SYNC_POLICY"] = "rules"
    fallback_id = insert_memory(
        "A recent novel policy fallback configuration check.",
        f"phase5-rules-{suffix}",
    )
    fallback_records = get_mutable_shard(f"phase5-rules-{suffix}").scroll(
        ScrollRequest(limit=10, with_payload=True)
    )[0]
    fallback = next(record for record in fallback_records if str(record.id) == fallback_id)
    assert fallback.payload["sync_reason"].startswith("sync:")
    assert queued_count(f"phase5-rules-{suffix}") == 1
    print(
        f"RULES_FALLBACK=PASS decision={fallback.payload['sync_decision']} "
        f"reason={fallback.payload['sync_reason']}"
    )
    os.environ["SYNC_POLICY"] = "model"


def verify_full_pipeline() -> None:
    base_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = os.getenv("QDRANT_COLLECTION", "field_memories")
    suffix = uuid.uuid4().hex[:8]
    device_a = f"phase5-a-{suffix}"
    device_b = f"phase5-b-{suffix}"
    point_id = str(uuid.uuid4())
    timestamp_a = time.time()
    timestamp_b = timestamp_a + 1.0
    text_a = "Device A found fresh water supplies near the east ridge."
    text_b = "Device B found the east ridge water cache empty after evacuation."
    client = QdrantClient(url=base_url)

    try:
        os.environ["OFFLINE"] = "1"
        id_a = insert_memory(
            text_a,
            device_a,
            point_id=point_id,
            timestamp=timestamp_a,
        )
        id_b = insert_memory(
            text_b,
            device_b,
            point_id=point_id,
            timestamp=timestamp_b,
        )
        assert id_a == id_b == point_id
        for device in (device_a, device_b):
            records = get_mutable_shard(device).scroll(
                ScrollRequest(limit=10, with_payload=True)
            )[0]
            assert records[0].payload["sync_decision"] == "sync"
            assert "trained logistic regression" in records[0].payload["sync_reason"]
            assert queued_count(device) == 1

        os.environ["OFFLINE"] = "0"
        report_a = run_sync_once(device_a)
        report_b = run_sync_once(device_b)
        server_points = client.retrieve(collection_name, [point_id], with_payload=True)
        assert len(server_points) == 1
        winner = server_points[0]
        assert winner.payload["device_id"] == device_b
        assert winner.payload["text"] == text_b
        assert float(winner.payload["timestamp"]) == timestamp_b
        assert report_b["conflicts"] and report_b["conflicts"][-1]["winner"] == device_b

        conflict_records = read_conflicts(point_id)
        assert conflict_records and conflict_records[-1]["winner"] == device_b
        sync_events = read_sync_log(limit=100)
        relevant_sync_events = [
            event
            for event in sync_events
            if event.get("device_id") in {device_a, device_b}
            and event.get("event") == "sync_completed"
        ]
        assert {event["device_id"] for event in relevant_sync_events} == {
            device_a,
            device_b,
        }
        assert any(event.get("conflicts") for event in relevant_sync_events)

        counts_a = shard_counts(device_a)
        counts_b = shard_counts(device_b)
        assert counts_a["mutable"] == counts_b["mutable"] == 0
        assert counts_a["immutable"] >= 1 and counts_b["immutable"] >= 1
        print(
            f"FULL_PIPELINE=PASS point_id={point_id} "
            f"device_a={device_a} device_b={device_b} "
            f"server_winner={winner.payload['device_id']}"
        )
        print(
            f"SYNC_LOG=PASS events={len(relevant_sync_events)} "
            f"uploads={sum(event.get('uploaded', 0) for event in relevant_sync_events)} "
            f"conflict_events={sum(len(event.get('conflicts', [])) for event in relevant_sync_events)}"
        )
        print(
            f"CONFLICT_VIEW_DATA=PASS matching_records={len(conflict_records)} "
            f"winner={conflict_records[-1]['winner']}"
        )
        print(
            f"SHARD_COUNTS device_a={counts_a} device_b={counts_b}"
        )
        print(
            f"PHASE5_PIPELINE_OK uploaded_a={report_a['uploaded']} "
            f"uploaded_b={report_b['uploaded']} winner={winner.payload['device_id']}"
        )
    finally:
        client.close()
        os.environ["OFFLINE"] = "0"
        os.environ["SYNC_POLICY"] = "model"
        close_all_shards()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    verify_model_metrics()
    verify_policy_switch()
    verify_full_pipeline()
    print("PHASE5_SMOKE_OK")


if __name__ == "__main__":
    main()