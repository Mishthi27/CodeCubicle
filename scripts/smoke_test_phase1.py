import os
import socket
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["OFFLINE"] = "1"

from src.embeddings import EMBEDDING_DIMENSION, MODEL_NAME, embed
from src.read_path import search
from src.shard import close_all_shards
from src.write_path import insert_memory


def main() -> None:
    warmup_vector = embed("Warm up the local embedding model before offline checks.")
    assert len(warmup_vector) == EMBEDDING_DIMENSION

    device_id = f"phase1-smoke-{uuid.uuid4().hex[:8]}"
    memories = [
        "Valve 3 pressure reading is 42 psi during the morning inspection.",
        "Radio battery was replaced before the mountain field survey.",
        "Map coordinates mark the damaged footbridge near the north trail.",
        "Water pump filter was clear after the afternoon maintenance check.",
        "Emergency beacon test reached the ridge station without signal loss.",
        "Generator fuel gauge showed half capacity at the remote camp.",
    ]
    query_texts = (
        "pressure readings for valve inspection",
        "radio battery condition in the field",
        "location of the damaged bridge",
    )
    blocked_attempts = 0

    def deny_network(*args, **kwargs):
        nonlocal blocked_attempts
        blocked_attempts += 1
        raise AssertionError("network connection attempted during offline smoke test")

    try:
        with (
            patch.object(socket.socket, "connect", side_effect=deny_network),
            patch.object(socket.socket, "connect_ex", side_effect=deny_network),
            patch.object(socket, "create_connection", side_effect=deny_network),
        ):
            point_ids = [
                insert_memory(text, device_id, "low") for text in memories
            ]
            assert len(set(point_ids)) == len(memories)

            latencies_ms = []
            all_results = []
            for query_text in query_texts:
                started = time.perf_counter()
                results = search(query_text, top_k=3, device_id=device_id)
                latencies_ms.append((time.perf_counter() - started) * 1000)
                assert results, f"no results for query: {query_text}"
                all_results.extend(results)
                print(
                    f"QUERY {query_text!r}: hits={len(results)} "
                    f"wall_ms={latencies_ms[-1]:.2f}"
                )

            expected_payload_fields = {
                "text",
                "device_id",
                "timestamp",
                "access_count",
                "last_accessed",
                "size_bytes",
                "sensitivity",
                "sync_status",
            }
            payload = all_results[0]["payload"]
            assert expected_payload_fields <= payload.keys()
            assert payload["device_id"] == device_id
            assert payload["access_count"] == 0
            assert payload["last_accessed"] == payload["timestamp"]
            assert payload["size_bytes"] == len(payload["text"].encode("utf-8"))
            assert payload["sensitivity"] == "low"
            assert payload["sync_status"] == "local_only"

        assert blocked_attempts == 0
        assert max(latencies_ms) < 1000, f"search exceeded 1 second: {latencies_ms}"
        print(f"MODEL={MODEL_NAME} DIMENSION={len(warmup_vector)}")
        print(
            "LATENCY_MS "
            f"min={min(latencies_ms):.2f} "
            f"mean={sum(latencies_ms) / len(latencies_ms):.2f} "
            f"max={max(latencies_ms):.2f}"
        )
        print("OFFLINE_SOCKET_GUARD=PASS blocked_attempts=0 OFFLINE=1")
        print(f"PAYLOAD_FIELDS=PASS fields={','.join(sorted(expected_payload_fields))}")
        print(
            f"PHASE1_SMOKE_OK inserted={len(point_ids)} "
            f"queries={len(query_texts)} device_id={device_id}"
        )
    finally:
        close_all_shards()


if __name__ == "__main__":
    main()