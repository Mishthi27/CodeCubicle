import argparse
import os
import socket
import sys
import uuid
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--offline-branch", action="store_true")
args = parser.parse_args()
os.environ["OFFLINE"] = "1" if args.offline_branch else "0"

from qdrant_client import QdrantClient
from qdrant_edge import ScrollRequest

from src.read_path import search
from src.shard import (
    close_all_shards,
    get_immutable_shard,
    get_mutable_shard,
)
from src.sync_worker import queued_count, run_sync_once
from src.write_path import insert_memory


def run_online() -> None:
    base_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = os.getenv("QDRANT_COLLECTION", "field_memories")
    device_id = f"phase3-smoke-{uuid.uuid4().hex[:8]}"
    memory_texts = (
        "A field report records river gauge level at 2.4 meters.",
        "The north trail radio relay battery was replaced this morning.",
    )

    client = QdrantClient(url=base_url)
    try:
        count_before = client.count(collection_name=collection_name, exact=True).count
        point_ids = [insert_memory(text, device_id) for text in memory_texts]
        mutable = get_mutable_shard(device_id)
        immutable = get_immutable_shard(device_id)
        mutable_before = len(
            mutable.scroll(ScrollRequest(limit=100, with_payload=True))[0]
        )
        assert mutable_before == len(point_ids)
        assert queued_count(device_id) == len(point_ids)

        report = run_sync_once(device_id)
        server_points = client.retrieve(collection_name, point_ids)
        server_ids = {str(point.id) for point in server_points}
        server_count = client.count(collection_name=collection_name, exact=True).count
        mutable_after = mutable.scroll(ScrollRequest(limit=100))[0]
        immutable_after = immutable.scroll(ScrollRequest(limit=100))[0]
        immutable_ids = {str(point.id) for point in immutable_after}

        assert server_ids == set(point_ids)
        assert all(point.payload.get("sync_status") == "synced" for point in server_points)
        assert not mutable_after, f"mutable shard still contains {len(mutable_after)} points"
        assert set(point_ids) <= immutable_ids
        assert all(
            dict(point.payload or {}).get("sync_status") == "synced"
            for point in immutable_after
            if str(point.id) in point_ids
        )
        assert queued_count(device_id) == 0
        assert report["uploaded"] == len(point_ids)
        assert report["purged"] == len(point_ids)

        print(
            f"SERVER_POINT_COUNT before={count_before} after={server_count} "
            f"uploaded={len(server_points)}"
        )
        print(
            f"SHARDS before_mutable={mutable_before} after_mutable={len(mutable_after)} "
            f"immutable_after={len(immutable_after)} restored={len(point_ids)}"
        )
        print(
            f"SYNC_STATUS server={','.join(sorted({p.payload['sync_status'] for p in server_points}))} "
            "immutable=synced queue_after=0"
        )
        print(
            f"PARTIAL_SNAPSHOT=PASS bytes={report['snapshot_bytes']} "
            f"purged={report['purged']} cutoff={report['purged_cutoff']:.6f}"
        )
        print(f"SYNC_ROUND_TRIP_MS={report['round_trip_ms']:.2f}")
        print(f"PHASE3_ONLINE_OK device_id={device_id} points={len(point_ids)}")
    finally:
        client.close()
        close_all_shards()


def run_offline() -> None:
    device_id = f"phase3-offline-{uuid.uuid4().hex[:8]}"
    text = "Offline branch note: the field radio remains operational."
    blocked_attempts = 0

    def deny_network(*args, **kwargs):
        nonlocal blocked_attempts
        blocked_attempts += 1
        raise AssertionError("network connection attempted in OFFLINE=1 branch")

    try:
        with (
            patch.object(socket.socket, "connect", side_effect=deny_network),
            patch.object(socket.socket, "connect_ex", side_effect=deny_network),
            patch.object(socket, "create_connection", side_effect=deny_network),
        ):
            point_id = insert_memory(text, device_id)
            report = run_sync_once(device_id)
            results = search("field radio operational", top_k=3, device_id=device_id)
            mutable_points = get_mutable_shard(device_id).scroll(
                ScrollRequest(limit=10, with_payload=True)
            )[0]
            immutable_points = get_immutable_shard(device_id).scroll(
                ScrollRequest(limit=10, with_payload=True)
            )[0]

        assert report["offline"] is True
        assert blocked_attempts == 0
        assert any(result["id"] == point_id for result in results)
        assert any(str(point.id) == point_id for point in mutable_points)
        assert not immutable_points
        assert queued_count(device_id) == 1
        print("offline, skipping sync")
        print(
            "OFFLINE_BRANCH=PASS "
            f"blocked_attempts={blocked_attempts} local_hits={len(results)} "
            f"mutable={len(mutable_points)} immutable={len(immutable_points)} "
            f"queued={queued_count(device_id)}"
        )
        print(f"PHASE3_OFFLINE_OK device_id={device_id}")
    finally:
        close_all_shards()


if __name__ == "__main__":
    if args.offline_branch:
        run_offline()
    else:
        run_online()