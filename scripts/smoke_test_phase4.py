import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient
from qdrant_edge import ScrollRequest

from src.conflict import local_version_wins, read_conflicts
from src.policy_rules import decide
from src.shard import close_all_shards, get_mutable_shard
from src.sync_worker import queued_count, run_sync_once
from src.write_path import insert_memory


def policy_cases() -> list[tuple[str, dict, float, str]]:
    now = time.time()
    ordinary = {
        "timestamp": now,
        "access_count": 0,
        "size_bytes": 256,
        "sensitivity": "low",
    }
    return [
        ("recent novel", ordinary, 0.10, "sync"),
        ("frequently used", {**ordinary, "access_count": 5}, 0.90, "sync"),
        ("stale novel", {**ordinary, "timestamp": now - 30 * 86400}, 0.10, "keep_local"),
        ("near duplicate", ordinary, 0.95, "keep_local"),
        ("large memory", {**ordinary, "size_bytes": 12000}, 0.10, "keep_local"),
        ("high sensitivity", {**ordinary, "sensitivity": "high"}, 0.10, "keep_local"),
    ]


def verify_policy() -> None:
    print("POLICY_DECISIONS")
    for label, payload, similarity, expected in policy_cases():
        decision, confidence, reason = decide(payload, similarity)
        assert decision == expected, f"{label}: expected {expected}, got {decision}"
        print(
            f"{label}: {decision} confidence={confidence:.2f} "
            f"similarity={similarity:.2f} reason={reason}"
        )


def verify_real_conflict() -> None:
    base_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = os.getenv("QDRANT_COLLECTION", "field_memories")
    suffix = uuid.uuid4().hex[:8]
    device_a = f"phase4-a-{suffix}"
    device_b = f"phase4-b-{suffix}"
    point_id = str(uuid.uuid4())
    timestamp_a = time.time()
    timestamp_b = timestamp_a + 1.0
    text_a = "Device A reports the north bridge is open to foot traffic."
    text_b = "Device B reports the north bridge is closed after storm damage."
    client = QdrantClient(url=base_url)

    try:
        os.environ["OFFLINE"] = "1"
        insert_memory(text_a, device_a, point_id=point_id, timestamp=timestamp_a)
        insert_memory(text_b, device_b, point_id=point_id, timestamp=timestamp_b)
        assert queued_count(device_a) == 1
        assert queued_count(device_b) == 1

        rejected_device = f"phase4-local-{suffix}"
        rejected_id = insert_memory(
            "Highly sensitive field source location: restricted access.",
            rejected_device,
            sensitivity="high",
        )
        rejected_records = get_mutable_shard(rejected_device).scroll(
            ScrollRequest(limit=10, with_payload=True)
        )[0]
        rejected = next(record for record in rejected_records if str(record.id) == rejected_id)
        assert rejected.payload["sync_decision"] == "keep_local"
        assert "high sensitivity" in rejected.payload["sync_reason"]
        assert queued_count(rejected_device) == 0

        offline_report = run_sync_once(device_a)
        assert offline_report["offline"] is True
        print(
            f"TWO_DEVICE_OFFLINE=PASS point_id={point_id} "
            f"device_a={device_a} device_b={device_b}"
        )
        print(
            "POLICY_GATE=PASS "
            f"decision={rejected.payload['sync_decision']} "
            f"queued={queued_count(rejected_device)} "
            f"reason={rejected.payload['sync_reason']}"
        )

        os.environ["OFFLINE"] = "0"
        report_a = run_sync_once(device_a)
        report_b = run_sync_once(device_b)
        local_only_report = run_sync_once(rejected_device)
        server_points = client.retrieve(collection_name, [point_id], with_payload=True)
        rejected_server_points = client.retrieve(
            collection_name,
            [rejected_id],
            with_payload=True,
        )
        assert len(server_points) == 1
        server_point = server_points[0]
        assert str(server_point.payload["device_id"]) == device_b
        assert float(server_point.payload["timestamp"]) == timestamp_b
        assert server_point.payload["text"] == text_b
        assert report_a["uploaded"] == 1
        assert report_b["uploaded"] == 1
        assert local_only_report["uploaded"] == 0
        assert not rejected_server_points
        assert len(report_b["conflicts"]) == 1

        conflict = report_b["conflicts"][0]
        assert conflict["point_id"] == point_id
        assert conflict["winner"] == device_b
        assert conflict["resolution"] == "last_write_wins"
        assert conflict["local_version"]["device_id"] == device_b
        assert conflict["server_version"]["device_id"] == device_a
        logged_conflicts = read_conflicts(point_id)
        assert logged_conflicts and logged_conflicts[-1] == conflict
        assert local_version_wins(
            {"timestamp": 10.0, "device_id": "device-z"},
            {"timestamp": 10.0, "device_id": "device-a"},
        )

        print("CONFLICT_RECORD=" + json.dumps(conflict, sort_keys=True))
        print(
            f"CONFLICT_RESOLUTION=PASS server_winner={server_point.payload['device_id']} "
            f"timestamp={server_point.payload['timestamp']} "
            f"logged={len(logged_conflicts)} reason={conflict['reason']}"
        )
        print(
            "PHASE4_CONFLICT_OK "
            f"device_a_uploaded={report_a['uploaded']} "
            f"device_b_uploaded={report_b['uploaded']} "
            f"server_id={server_point.id}"
        )
    finally:
        client.close()
        close_all_shards()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    verify_policy()
    verify_real_conflict()
    print("PHASE4_SMOKE_OK")


if __name__ == "__main__":
    main()