import json
import math
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SYNC_POLICY"] = "model"

from qdrant_client import QdrantClient
from qdrant_edge import ScrollRequest

from src.conflict import read_conflicts
from src.llm import answer
from src.read_path import search
from src.shard import close_all_shards, get_mutable_shard
from src.sync_worker import read_sync_log, run_sync_once
from src.write_path import insert_memory


def run_round(round_number: int, client: QdrantClient, collection_name: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    device_a = f"device-a-phase6-{suffix}"
    device_b = f"device-b-phase6-{suffix}"
    point_id = str(uuid.uuid4())
    timestamp_a = time.time()
    timestamp_b = timestamp_a + 1.0
    text_a = f"Round {round_number}: Device A reports the west pump is running normally."
    text_b = f"Round {round_number}: Device B reports the west pump stopped after a power surge."

    process_env = os.environ.copy()
    process_env.update({"OFFLINE": "1", "SYNC_POLICY": "model"})
    processes = []
    for device_id, timestamp, memory_text in (
        (device_a, timestamp_a, text_a),
        (device_b, timestamp_b, text_b),
    ):
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src.device",
                "--device-id",
                device_id,
                "add",
                "--point-id",
                point_id,
                "--timestamp",
                str(timestamp),
            ],
            cwd=ROOT,
            env=process_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        processes.append((device_id, process, memory_text))

    process_outputs = {}
    for device_id, process, memory_text in processes:
        stdout, stderr = process.communicate(input=memory_text, timeout=180)
        if process.returncode != 0:
            raise RuntimeError(
                f"device process failed for {device_id}:\n{stdout}\n{stderr}"
            )
        if f"Inserted memory id={point_id}" not in stdout:
            raise AssertionError(f"unexpected add output for {device_id}: {stdout}")
        process_outputs[device_id] = stdout.strip()

    os.environ["OFFLINE"] = "1"
    local_results = search("west pump power surge", top_k=5, device_id=device_b)
    assert any(result["id"] == point_id for result in local_results)
    local_record = next(
        record
        for record in get_mutable_shard(device_b).scroll(
            ScrollRequest(limit=10, with_payload=True)
        )[0]
        if str(record.id) == point_id
    )
    assert local_record.payload["sync_decision"] == "sync"
    assert local_record.payload["sync_status"] == "local_only"

    os.environ["OFFLINE"] = "0"
    report_a = run_sync_once(device_a)
    report_b = run_sync_once(device_b)
    server_points = client.retrieve(collection_name, [point_id], with_payload=True)
    assert len(server_points) == 1
    winner = server_points[0]
    assert winner.payload["device_id"] == device_b
    assert winner.payload["text"] == text_b
    assert math.isclose(
        float(winner.payload["timestamp"]),
        timestamp_b,
        rel_tol=0.0,
        abs_tol=1e-3,
    )
    assert report_a["uploaded"] == report_b["uploaded"] == 1
    assert report_b["conflicts"][-1]["winner"] == device_b

    conflicts = read_conflicts(point_id)
    assert conflicts and conflicts[-1]["winner"] == device_b
    sync_entries = read_sync_log(limit=100)
    round_events = [
        event
        for event in sync_entries
        if event.get("device_id") in {device_a, device_b}
        and event.get("event") == "sync_completed"
    ]
    assert len(round_events) == 2
    assert any(event.get("conflicts") for event in round_events)

    counts_a = {
        "mutable": len(get_mutable_shard(device_a).scroll(ScrollRequest(limit=10))[0]),
    }
    counts_b = {
        "mutable": len(get_mutable_shard(device_b).scroll(ScrollRequest(limit=10))[0]),
    }
    assert counts_a["mutable"] == counts_b["mutable"] == 0
    print(f"DEVICE_A_PROCESS={process_outputs[device_a]}")
    print(f"DEVICE_B_PROCESS={process_outputs[device_b]}")
    print(
        f"ROUND_{round_number}_PASS point_id={point_id} "
        f"offline_hits={len(local_results)} winner={winner.payload['device_id']} "
        f"sync_events={len(round_events)} conflict_records={len(conflicts)} "
        f"mutable_a=0 mutable_b=0"
    )
    print(
        f"SYNC_ROUND_TRIP_MS device_a={report_a['round_trip_ms']:.2f} "
        f"device_b={report_b['round_trip_ms']:.2f}"
    )
    close_all_shards()
    return {
        "round": round_number,
        "point_id": point_id,
        "device_a": device_a,
        "device_b": device_b,
        "winner": winner.payload["device_id"],
        "conflict": conflicts[-1],
    }


def verify_local_ask() -> None:
    os.environ["OFFLINE"] = "1"
    device_id = f"phase6-ask-{uuid.uuid4().hex[:8]}"
    blocked_attempts = 0

    def deny_network(*args, **kwargs):
        nonlocal blocked_attempts
        blocked_attempts += 1
        raise AssertionError("local Ask attempted a network connection")

    try:
        with (
            patch.object(socket.socket, "connect", side_effect=deny_network),
            patch.object(socket.socket, "connect_ex", side_effect=deny_network),
            patch.object(socket, "create_connection", side_effect=deny_network),
        ):
            insert_memory(
                "The west pump uses a 12 volt replacement battery.",
                device_id,
            )
            results = search("What voltage battery does the west pump use?", 3, device_id)
            response = answer("What voltage battery does the west pump use?", results)

        assert results and blocked_attempts == 0
        assert "12 volt" in response
        print(
            f"ASK_OFFLINE=PASS blocked_attempts={blocked_attempts} "
            f"sources={len(results)} answer={response}"
        )
    finally:
        close_all_shards()
        os.environ["OFFLINE"] = "0"


def main() -> None:
    os.environ["OFFLINE"] = "0"
    verify_local_ask()
    base_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = os.getenv("QDRANT_COLLECTION", "field_memories")
    client = QdrantClient(url=base_url)
    try:
        if not client.collection_exists(collection_name):
            raise RuntimeError(
                f"Qdrant collection {collection_name!r} is missing; complete Phase 3 first"
            )
        round_results = [
            run_round(number, client, collection_name)
            for number in (1, 2)
        ]
        print("PHASE6_ROUNDS=" + json.dumps(round_results, sort_keys=True))
        print("PHASE6_SMOKE_OK rounds=2 device_processes=4")
    finally:
        os.environ["OFFLINE"] = "0"
        os.environ["SYNC_POLICY"] = "model"
        client.close()
        close_all_shards()


if __name__ == "__main__":
    main()