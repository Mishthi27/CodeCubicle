import logging
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qdrant_edge import Point, Query, QueryRequest, ScrollRequest, UpdateOperation

from src.embeddings import embed
from src.read_path import list_memories, search
from src.shard import (
    VECTOR_NAME,
    close_all_shards,
    get_immutable_shard,
    get_mutable_shard,
)
from src.write_path import insert_memory


def upsert_text(shard, point_id: str, text: str, device_id: str, timestamp: float):
    shard.update(
        UpdateOperation.upsert_points(
            [
                Point(
                    id=point_id,
                    vector={VECTOR_NAME: embed(text)},
                    payload={
                        "text": text,
                        "device_id": device_id,
                        "timestamp": timestamp,
                        "access_count": 0,
                        "last_accessed": timestamp,
                        "size_bytes": len(text.encode("utf-8")),
                        "sensitivity": "low",
                        "sync_status": "synced",
                    },
                )
            ]
        )
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    device_id = f"phase2-smoke-{uuid.uuid4().hex[:8]}"
    mutable = get_mutable_shard(device_id)
    immutable = get_immutable_shard(device_id)
    try:
        mutable_id = insert_memory(
            "A field note about the river crossing and damaged footbridge.",
            device_id,
        )
        empty_results = search("river crossing footbridge", 10, device_id)
        assert [result["id"] for result in empty_results] == [mutable_id]
        assert not immutable.scroll(ScrollRequest(limit=1))[0]
        print(
            "EMPTY_IMMUTABLE_PASSTHROUGH=PASS "
            f"mutable_hits={len(empty_results)} immutable_hits=0"
        )

        duplicate_id = str(uuid.uuid4())
        mutable_unique_id = str(uuid.uuid4())
        immutable_unique_id = str(uuid.uuid4())
        upsert_text(
            mutable,
            duplicate_id,
            "The river crossing footbridge is damaged after the storm.",
            device_id,
            100.0,
        )
        upsert_text(
            mutable,
            mutable_unique_id,
            "Field repair supplies are stored at the river camp.",
            device_id,
            101.0,
        )
        upsert_text(
            immutable,
            duplicate_id,
            "The river crossing footbridge is closed after storm damage.",
            device_id,
            102.0,
        )
        upsert_text(
            immutable,
            immutable_unique_id,
            "A trail marker points east beyond the river crossing.",
            device_id,
            103.0,
        )

        query_text = "river crossing footbridge storm"
        started = time.perf_counter()
        results = search(query_text, 10, device_id)
        latency_ms = (time.perf_counter() - started) * 1000
        result_ids = [result["id"] for result in results]
        assert len(result_ids) == len(set(result_ids)), "duplicate point IDs in merged results"
        assert set(result_ids) == {
            mutable_id,
            duplicate_id,
            mutable_unique_id,
            immutable_unique_id,
        }
        assert results == sorted(results, key=lambda result: result["score"], reverse=True)

        query_vector = embed(query_text)
        duplicate_scores = []
        for shard in (mutable, immutable):
            shard_matches = shard.query(
                QueryRequest(
                    query=Query.Nearest(query_vector, using=VECTOR_NAME),
                    limit=10,
                    with_payload=True,
                    with_vector=False,
                )
            )
            duplicate_scores.extend(
                float(match.score)
                for match in shard_matches
                if str(match.id) == duplicate_id
            )
        duplicate_result = next(result for result in results if result["id"] == duplicate_id)
        assert duplicate_result["score"] == max(duplicate_scores)

        memories = list_memories(device_id)
        listed_ids = [item["id"] for item in memories]
        assert len(listed_ids) == len(set(listed_ids))
        assert set(listed_ids) == set(result_ids)

        raw_mutable_count = len(mutable.scroll(ScrollRequest(limit=100))[0])
        raw_immutable_count = len(immutable.scroll(ScrollRequest(limit=100))[0])
        print(
            f"DEDUP=PASS before={raw_mutable_count + raw_immutable_count} "
            f"after={len(results)} duplicates_removed=1"
        )
        print(
            f"MERGE_ORDER=PASS top_k=10 latency_ms={latency_ms:.2f} "
            f"duplicate_score={duplicate_result['score']:.4f} "
            f"best_source_score={max(duplicate_scores):.4f}"
        )
        print(
            f"MEMORY_LIST=PASS listed={len(memories)} "
            f"mutable={raw_mutable_count} immutable={raw_immutable_count}"
        )
        print(
            "PHASE2_SMOKE_OK "
            f"mutable={raw_mutable_count} immutable={raw_immutable_count} "
            f"unique_results={len(results)}"
        )
    finally:
        close_all_shards()


if __name__ == "__main__":
    main()