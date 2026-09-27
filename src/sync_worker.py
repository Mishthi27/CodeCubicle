import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from qdrant_edge import (
    FieldCondition,
    Filter,
    Point,
    RangeFloat,
    ScrollRequest,
    UpdateOperation,
)

from src.embeddings import EMBEDDING_DIMENSION
from src.conflict import append_conflict, make_conflict_record
from src.shard import (
    VECTOR_NAME,
    get_immutable_shard,
    get_mutable_shard,
)


load_dotenv()
logger = logging.getLogger(__name__)

upload_queue: list[tuple[str, Point]] = []
_queue_lock = threading.Lock()
_sync_lock = threading.Lock()
_workers: dict[str, tuple[threading.Event, threading.Thread]] = {}


def enqueue_point(device_id: str, point: Point) -> None:
    with _queue_lock:
        upload_queue.append((device_id, point))


def queued_count(device_id: str | None = None) -> int:
    with _queue_lock:
        if device_id is None:
            return len(upload_queue)
        return sum(queued_device == device_id for queued_device, _ in upload_queue)


def _is_offline() -> bool:
    return os.getenv("OFFLINE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _scroll_all(shard, with_vector: bool = False) -> list:
    records = []
    offset = None
    while True:
        page, offset = shard.scroll(
            ScrollRequest(
                offset=offset,
                limit=256,
                with_payload=True,
                with_vector=with_vector,
            )
        )
        records.extend(page)
        if offset is None or len(page) < 256:
            return records


def _pending_points(device_id: str) -> list[Point]:
    mutable = get_mutable_shard(device_id)
    points_by_id = {}
    for record in _scroll_all(mutable, with_vector=True):
        payload = dict(record.payload or {})
        if payload.get("sync_status") != "local_only":
            continue
        if payload.get("sync_decision", "sync") != "sync":
            continue
        if record.vector is None:
            raise RuntimeError(f"mutable point {record.id} has no vector")
        points_by_id[str(record.id)] = Point(
            id=str(record.id),
            vector=dict(record.vector),
            payload=payload,
        )

    with _queue_lock:
        queued_for_device = [
            point for queued_device, point in upload_queue if queued_device == device_id
        ]
    for point in queued_for_device:
        points_by_id[str(point.id)] = point

    return list(points_by_id.values())


def _ensure_collection(client: QdrantClient, collection_name: str) -> None:
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                VECTOR_NAME: models.VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=models.Distance.COSINE,
                )
            },
        )


def _create_partial_snapshot(
    base_url: str,
    collection_name: str,
    shard,
) -> int:
    manifest = shard.snapshot_manifest()
    endpoint = (
        f"{base_url.rstrip('/')}/collections/{quote(collection_name, safe='')}"
        "/shards/0/snapshot/partial/create"
    )
    request = Request(
        endpoint,
        data=json.dumps(manifest).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        snapshot_bytes = response.read()

    if not snapshot_bytes:
        raise RuntimeError("Qdrant returned an empty partial snapshot")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".snapshot", delete=False) as snapshot_file:
            snapshot_file.write(snapshot_bytes)
            temporary_path = snapshot_file.name
        shard.update_from_snapshot(temporary_path)
    finally:
        if temporary_path and Path(temporary_path).exists():
            Path(temporary_path).unlink()

    return len(snapshot_bytes)


def run_sync_once(
    device_id: str,
    offline: bool | None = None,
) -> dict:
    if offline is None:
        offline = _is_offline()
    if offline:
        logger.info("offline, skipping sync")
        return {"offline": True, "uploaded": 0, "pulled": 0, "purged": 0}

    with _sync_lock:
        points = _pending_points(device_id)
        if not points:
            logger.info("no pending points for device_id=%s", device_id)
            return {"offline": False, "uploaded": 0, "pulled": 0, "purged": 0}

        base_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        collection_name = os.getenv("QDRANT_COLLECTION", "field_memories")
        mutable = get_mutable_shard(device_id)
        immutable = get_immutable_shard(device_id)
        mutable_before = len(_scroll_all(mutable))
        cutoff = max(float(point.payload["timestamp"]) for point in points)
        client = QdrantClient(url=base_url)
        try:
            _ensure_collection(client, collection_name)
            existing_by_id = {
                str(server_point.id): server_point
                for server_point in client.retrieve(
                    collection_name=collection_name,
                    ids=[str(point.id) for point in points],
                    with_payload=True,
                    with_vectors=False,
                )
            }
            points_to_upload = []
            conflict_records = []
            for point in points:
                server_point = existing_by_id.get(str(point.id))
                if server_point is None:
                    points_to_upload.append(point)
                    continue

                conflict = make_conflict_record(
                    str(point.id),
                    dict(point.payload or {}),
                    dict(server_point.payload or {}),
                )
                if conflict is None:
                    continue

                conflict_records.append(conflict)
                local_wins = conflict["winner"] == str(
                    dict(point.payload or {}).get("device_id", "unknown")
                )
                if local_wins:
                    points_to_upload.append(point)

            server_points = [
                models.PointStruct(
                    id=str(point.id),
                    vector=dict(point.vector),
                    payload={**dict(point.payload), "sync_status": "synced"},
                )
                for point in points_to_upload
            ]
            if server_points:
                client.upsert(
                    collection_name=collection_name,
                    points=server_points,
                    wait=True,
                )

            for conflict in conflict_records:
                append_conflict(conflict)
                logger.warning("conflict resolved: %s", conflict["reason"])

            snapshot_bytes = _create_partial_snapshot(
                base_url,
                collection_name,
                immutable,
            )

            synced_ids = {str(point.id) for point in points}
            purge_filter = Filter(
                must=[
                    FieldCondition(
                        key="timestamp",
                        range=RangeFloat(lte=cutoff),
                    )
                ]
            )
            remaining_synced_ids = synced_ids
            for attempt in range(3):
                mutable.update(UpdateOperation.delete_points_by_filter(purge_filter))
                remaining_synced_ids = {
                    str(record.id)
                    for record in _scroll_all(mutable)
                    if str(record.id) in synced_ids
                }
                if not remaining_synced_ids:
                    break
                logger.warning(
                    "timestamp purge retry=%s remaining_uploaded_points=%s",
                    attempt + 1,
                    len(remaining_synced_ids),
                )
            if remaining_synced_ids:
                logger.warning(
                    "timestamp cutoff left uploaded IDs; applying exact-ID purge for %s points",
                    len(remaining_synced_ids),
                )
                mutable.update(
                    UpdateOperation.delete_points(sorted(remaining_synced_ids))
                )
                remaining_synced_ids = {
                    str(record.id)
                    for record in _scroll_all(mutable)
                    if str(record.id) in synced_ids
                }
                if remaining_synced_ids:
                    raise RuntimeError(
                        "purge left uploaded points in mutable shard: "
                        + ", ".join(sorted(remaining_synced_ids))
                    )

            mutable_after = len(_scroll_all(mutable))
            immutable_after = len(_scroll_all(immutable))
            with _queue_lock:
                upload_queue[:] = [
                    (queued_device, queued_point)
                    for queued_device, queued_point in upload_queue
                    if not (
                        queued_device == device_id
                        and str(queued_point.id) in synced_ids
                    )
                ]

            logger.info(
                "sync complete device_id=%s uploaded=%s snapshot_bytes=%s purged_cutoff=%.6f",
                device_id,
                len(points),
                snapshot_bytes,
                cutoff,
            )
            return {
                "offline": False,
                "uploaded": len(points),
                "point_ids": sorted(synced_ids),
                "uploaded_ids": sorted(str(point.id) for point in points_to_upload),
                "conflicts": conflict_records,
                "snapshot_bytes": snapshot_bytes,
                "purged_cutoff": cutoff,
                "mutable_before": mutable_before,
                "mutable_after": mutable_after,
                "immutable_after": immutable_after,
                "purged": mutable_before - mutable_after,
            }
        finally:
            client.close()


def _worker_loop(device_id: str, interval_seconds: float, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            run_sync_once(device_id)
        except Exception:
            logger.exception("sync worker failed for device_id=%s", device_id)
        stop_event.wait(interval_seconds)


def start_sync_worker(device_id: str, interval_seconds: float = 5.0) -> None:
    existing = _workers.get(device_id)
    if existing and existing[1].is_alive():
        return
    stop_event = threading.Event()
    worker = threading.Thread(
        target=_worker_loop,
        args=(device_id, interval_seconds, stop_event),
        name=f"sync-{device_id}",
        daemon=True,
    )
    _workers[device_id] = (stop_event, worker)
    worker.start()


def stop_sync_worker(device_id: str, timeout: float = 5.0) -> None:
    worker_state = _workers.pop(device_id, None)
    if worker_state is None:
        return
    stop_event, worker = worker_state
    stop_event.set()
    worker.join(timeout)