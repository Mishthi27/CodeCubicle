import os
import re
from pathlib import Path

from qdrant_edge import Distance, EdgeConfig, EdgeShard, EdgeVectorParams

from src.embeddings import EMBEDDING_DIMENSION


VECTOR_NAME = "text"
DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_shards: dict[Path, EdgeShard] = {}


def _get_shard(device_id: str | None, shard_name: str) -> EdgeShard:
    device_id = device_id or os.getenv("DEVICE_ID", "device-a")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", device_id):
        raise ValueError("device_id may contain only letters, numbers, '_' and '-'")

    path = (DATA_ROOT / device_id / shard_name).resolve()
    if path in _shards:
        return _shards[path]

    path.mkdir(parents=True, exist_ok=True)
    config = EdgeConfig(
        vectors={
            VECTOR_NAME: EdgeVectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.Cosine,
            )
        }
    )
    if path.exists() and any(path.iterdir()):
        shard = EdgeShard.load(str(path), config)
    else:
        shard = EdgeShard.create(str(path), config)

    _shards[path] = shard
    return shard


def get_mutable_shard(device_id: str | None = None) -> EdgeShard:
    return _get_shard(device_id, "mutable")


def get_immutable_shard(device_id: str | None = None) -> EdgeShard:
    return _get_shard(device_id, "immutable")


def close_all_shards() -> None:
    shards = list(_shards.values())
    _shards.clear()
    for shard in shards:
        try:
            shard.flush()
        finally:
            shard.close()