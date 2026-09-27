import json
import threading
from pathlib import Path

from src.shard import DATA_ROOT


CONFLICT_LOG_PATH = DATA_ROOT / "conflicts.jsonl"
_conflict_log_lock = threading.Lock()


def _version(payload: dict) -> dict:
    return {
        "device_id": str(payload.get("device_id", "unknown")),
        "timestamp": float(payload.get("timestamp", 0.0)),
        "text": str(payload.get("text", "")),
    }


def local_version_wins(local_payload: dict, server_payload: dict) -> bool:
    local = _version(local_payload)
    server = _version(server_payload)
    if local["timestamp"] != server["timestamp"]:
        return local["timestamp"] > server["timestamp"]
    return local["device_id"] > server["device_id"]


def make_conflict_record(
    point_id: str,
    local_payload: dict,
    server_payload: dict,
) -> dict | None:
    local = _version(local_payload)
    server = _version(server_payload)
    if local["text"] == server["text"]:
        return None

    local_wins = local_version_wins(local, server)
    winner = local["device_id"] if local_wins else server["device_id"]
    if local["timestamp"] == server["timestamp"]:
        reason = f"timestamp tie; lexicographically greater device_id wins ({winner})"
    else:
        reason = f"greater timestamp wins ({winner})"
    return {
        "point_id": str(point_id),
        "local_version": local,
        "server_version": server,
        "resolution": "last_write_wins",
        "winner": winner,
        "reason": reason,
    }


def append_conflict(record: dict) -> None:
    CONFLICT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _conflict_log_lock:
        with CONFLICT_LOG_PATH.open("a", encoding="utf-8") as conflict_log:
            conflict_log.write(line + "\n")


def read_conflicts(point_id: str | None = None) -> list[dict]:
    if not CONFLICT_LOG_PATH.exists():
        return []
    with CONFLICT_LOG_PATH.open("r", encoding="utf-8") as conflict_log:
        records = [json.loads(line) for line in conflict_log if line.strip()]
    if point_id is not None:
        records = [record for record in records if record["point_id"] == str(point_id)]
    return records