## Phase 0 — Environment & reference repo — 2026-09-27 12:54 +05:30

Status: PASS

What was built:
- Python 3.11.9 venv at `.venv` (system default is 3.14.2; official demo requires `>=3.11,<3.14` — logged and used 3.11).
- Pinned `requirements.txt`: qdrant-edge-py==0.8.0, qdrant-client==1.19.1, fastembed==0.8.1, streamlit==1.64.0, scikit-learn==1.9.1, python-dotenv==1.2.3.
- `.env.example` with `QDRANT_URL=http://localhost:6333`, `OFFLINE=0`, `DEVICE_ID=device-a`.
- Cloned `https://github.com/qdrant/qdrant-edge-demo` into `reference/qdrant-edge-demo/` (read-only; not edited).
- Qdrant server via Docker on port 6333 (`docker run -d --name qdrant -p 6333:6333 qdrant/qdrant`).
- Repo skeleton dirs: `src/`, `dashboard/`, `scripts/`, `data/` (Phase 1+ modules not written yet).
- Layout decision: project lives at this repo root (`CodeCubicle`), not a nested `field-memory-assistant/` folder, because `BUILD_PLAN.md` is already here.

What was run to verify it (commands + real output snippets):

1) Official demo deps + CLIP models (`uv sync` then the Makefile `setup` download steps; Windows has no `make`):

```
Vision model ready
Text model ready
```

Locked demo Edge version from `uv.lock`: **qdrant-edge-py 0.5.0** (our app pins **0.8.0**).

2) Official demo backend (`uv run uvicorn backend.server:app --host 0.0.0.0 --port 8000`):

```
C:\Users\mishthi\OneDrive - igdtuw.ac.in\Documents\GitHub\CodeCubicle\reference\qdrant-edge-demo\backend\server.py:33: UserWarning: Qdrant client version 1.16.2 is incompatible with server version 1.19.1. Major versions should match and minor version difference must not exceed 1. Set check_compatibility=False to skip version check.
  qdrant = QdrantClient(url=QDRANT_URL)
INFO:     Started server process [5440]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

3) Official demo **storage + encoder + upload queue + full snapshot restore** (their `VisionStorage` / `CrossModalEncoder`, not a stub):

```
EDGE_PKG 0.5.0
QDRANT_COLLECTIONS {"result":{"collections":[{"name":"smart_glasses"}]},"status":"ok","time":6.843e-6}
STORAGE_INIT_OK mutable= True
EMBED_SHAPE (512,) dim 512
STORE_OK 6840875b-1704-4c4e-96ee-99231e02428f queue 1
SEARCH_HITS [{'id': UUID('6840875b-1704-4c4e-96ee-99231e02428f'), 'score': 0.27235472202301025, 'image_path': 'demo-data\\images_phase0\\probe.png'}]
FORCE_SYNC_DONE queue 0
COLLECTIONS_AFTER_SYNC {"result": {"collections": [{"name": "smart_glasses"}]}, "status": "ok", "time": 4.429e-06}
SERVER_POINT_COUNT {"result": {"count": 1}, "status": "ok", "time": 0.003039953}
FULL_SYNC_OK immutable= True
SEARCH_AFTER_FULL_SYNC [{'id': UUID('6840875b-1704-4c4e-96ee-99231e02428f'), 'score': 0.27235472202301025, 'image_path': 'demo-data\\images_phase0\\probe.png'}]
DEMO_E2E_OK
```

4) Official Streamlit entrypoint (`uv run streamlit run app.py --server.headless true --server.port 8501`):

```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.1.10:8501
  External URL: http://45.119.31.119:8501
```

`curl.exe http://localhost:8501/` → `HTTP 200 bytes=1522`

5) Docker Qdrant `GET /collections`:

```
curl.exe -s http://localhost:6333/collections
{"result":{"collections":[{"name":"smart_glasses"}]},"status":"ok","time":0.000047716}
```

(empty collections `[]` was the first response before the demo backend created `smart_glasses`.)

6) **qdrant-edge-py 0.8.0** API probe in our venv (`EdgeShard.create` + named vectors + upsert + query):

Failed first attempt (`id="p1"`):

```
ValueError: failed to parse p1 as UUID: invalid character: found `p` at 0
while processing 'id'
CONFIG_OK EdgeConfig(vectors={"text": EdgeVectorParams(size=4, distance=Distance.Cosine, ...)})
CREATE_OK <class 'builtins.EdgeShard'>
```

Succeeded with a UUID id:

```
UPSERT_OK id= f375c9f9-4903-4deb-a872-1445d5ce8c1a
QUERY_RESULTS [ScoredPoint(id="f375c9f9-4903-4deb-a872-1445d5ce8c1a", version=0, score=1, vector=None, payload={"text": "hello"}, order_value=None)]
MANIFEST {'bfdcd48b-871d-4028-b15e-fa634c79550d': {'segment_id': 'bfdcd48b-871d-4028-b15e-fa634c79550d', 'segment_version': 0, 'file_versions': {...}}}
CLOSE_OK
```

Integration check with previous phases:
- N/A (first phase). Confirmed **venv + Docker Qdrant + reference demo** work in one session: 0.8.0 shard create/query in `.venv`, `localhost:6333/collections` returns JSON, demo 0.5.0 insert→search→upload→server count=1→full snapshot into immutable shard, Streamlit 200.

Known issues / TODOs carried forward:
- **Package name:** BUILD_PLAN says `qdrant-edge`; real PyPI package is `qdrant-edge-py`, import `qdrant_edge`.
- **Two Edge APIs:** demo lockfile is **0.5.0** (`EdgeShard(path, config)`, `EdgeConfig(vector_data=VectorDataConfig(size, distance))`, unnamed default vector). **0.8.0** (what we will use in Phase 1) matches current docs: `EdgeShard.create(path, config)` / `EdgeShard.load(path)`, `EdgeConfig(vectors={name: EdgeVectorParams(...)})`.
- **Point IDs:** must be UUID or unsigned integer. BUILD_PLAN example `"p123"` raises `ValueError` on 0.8.0. Phase 1 will use `uuid.uuid4()`.
- **upload_queue is not an EdgeShard API.** Demo uses `persistqueue.SQLiteAckQueue` (`glasses_x_edge/queue.py`). We must implement our own queue in Phase 3.
- **Partial snapshot:** demo backend POSTs to `http://localhost:6333/collections/{name}/shards/{shard_id}/snapshot/partial/create` with body = `immutable_shard.snapshot_manifest()`. Restore: `immutable_shard.update_from_snapshot(path)`. Full sync: download shard snapshot then `EdgeShard.unpack_snapshot(snapshot, dest)` + `EdgeShard.load`/`EdgeShard(path, None)` depending on version.
- **Purge:** `UpdateOperation.delete_points_by_filter(Filter(must=[FieldCondition(key=SYNC_TIMESTAMP_KEY, range=RangeFloat(lte=cutoff))]))` — timestamp cutoff on payload, not a built-in Edge method.
- Demo `qdrant-client==1.16.2` warns against Docker server **1.19.1**. Our `requirements.txt` pins client **1.19.1** to match the running server.
- Windows: no `make`; `uv` was installed via pip (not on PATH until full path used). Docker Desktop had to be started first.
- Qdrant container left running on 6333 after Phase 0. Streamlit/backend were stopped so they do not keep indexing `input.mp4`.

### Phase 1 method signatures we will use (0.8.0, verified)

```python
from qdrant_edge import (
    Distance,
    EdgeConfig,
    EdgeShard,
    EdgeVectorParams,
    Point,
    Query,
    QueryRequest,
    UpdateOperation,
)

VECTOR_NAME = "text"  # named vector; size must match embedder (bge-small-en is typically 384 — confirm in Phase 1)
config = EdgeConfig(
    vectors={VECTOR_NAME: EdgeVectorParams(size=VECTOR_DIM, distance=Distance.Cosine)}
)
shard = EdgeShard.create(str(path), config)          # new shard; fails if data already present
# shard = EdgeShard.load(str(path))                    # reopen

point = Point(
    id=str(uuid.uuid4()),                             # UUID string, not "p123"
    vector={VECTOR_NAME: embedding},                  # named vector dict
    payload={...},
)
shard.update(UpdateOperation.upsert_points([point]))

results = shard.query(
    QueryRequest(
        query=Query.Nearest(embedding, using=VECTOR_NAME),
        limit=5,
        with_payload=True,
        with_vector=False,
    )
)
# later: shard.snapshot_manifest(); shard.update_from_snapshot(path); shard.flush(); shard.close()
```

## Phase 1 — Mutable shard + local embeddings + offline search — 2026-09-27 16:13 +05:30

Status: PASS

What was built:
- `src/embeddings.py`: lazy local FastEmbed wrapper using `BAAI/bge-small-en-v1.5`; verified output dimension is 384.
- `src/shard.py`: cached mutable Edge shard per device at `data/<device-id>/mutable/`, configured with named `text` vector and cosine distance; reopens existing shards.
- `src/write_path.py`: inserts UUID points with the complete Phase 1 payload and `sync_status="local_only"`.
- `src/read_path.py`: embeds and searches the mutable shard only, returns payload and score, and logs wall-clock latency on every call.
- `src/device.py`: `add` and `search` stdin CLI with `--device-id`, sensitivity, and top-k options.
- `scripts/smoke_test_phase1.py`: inserts six memories and runs three searches with `OFFLINE=1` and socket connection entry points blocked.
- The first run exposed that Edge requires the shard directory itself to exist before `EdgeShard.create`; `src/shard.py` now creates it.

What was run to verify it (commands + real output snippets):

1) Real local model dimension check:

```text
MODEL=BAAI/bge-small-en-v1.5 DIMENSION= 384
```

The model was downloaded/cached before the offline checks. Model provisioning therefore needs connectivity once; insert and search use the local cache.

2) ` .\.venv\Scripts\python.exe scripts\smoke_test_phase1.py`:

```text
QUERY 'pressure readings for valve inspection': hits=3 wall_ms=14.77
QUERY 'radio battery condition in the field': hits=3 wall_ms=7.38
QUERY 'location of the damaged bridge': hits=3 wall_ms=7.32
MODEL=BAAI/bge-small-en-v1.5 DIMENSION=384
LATENCY_MS min=7.32 mean=9.82 max=14.77
OFFLINE_SOCKET_GUARD=PASS blocked_attempts=0 OFFLINE=1
PAYLOAD_FIELDS=PASS fields=access_count,device_id,last_accessed,sensitivity,size_bytes,sync_status,text,timestamp
PHASE1_SMOKE_OK inserted=6 queries=3 device_id=phase1-smoke-bf680ff3
```

3) Separate-process CLI persistence check (stdin `add`, then stdin `search` using the same generated device ID):

```text
Inserted memory id=2f4934f4-da40-4e97-9d39-40610acaf856
search latency_ms=651.88
"score": 0.9116009473800659
"text": "Field note: water pump inspection passed."
"sync_status": "local_only"
```

The CLI process measurement includes cold model initialization and remained below one second. Editor diagnostics reported no errors in the six Phase 1 files.

Integration check with previous phases:
- N/A (first implementation phase; no earlier application smoke tests exist). Phase 0's Qdrant server/reference checks are recorded above and were not changed by this phase.
- Phase 1 owns `data/<device-id>/mutable/`; Phase 2 must add `data/<device-id>/immutable/` beside it without renaming this directory.

Known issues / TODOs carried forward:
- The smoke test blocks Python socket connection entry points during insert/search and runs with `OFFLINE=1`; Wi-Fi/Ethernet was not physically disabled. No network call was attempted (zero blocked attempts).
- FastEmbed's model must be present in its local cache before a first-ever disconnected run. The verified model is cached on this machine.
- Qdrant server remains available from Phase 0, but Phase 1 performs no server calls.

## Phase 2 — Immutable shard + merge/dedupe + dashboard v1 — 2026-09-27 18:57 +05:30

Status: PASS

What was built:
- `src/shard.py`: adds an immutable Edge shard at `data/<device-id>/immutable/` using the same named 384-dimensional cosine vector config; existing mutable layout remains `data/<device-id>/mutable/`.
- `src/read_path.py`: searches both shards, sorts by score descending, deduplicates by point ID (retaining the higher-scoring copy), and lists/deduplicates memories from both shards using Edge's real scroll API.
- `dashboard/app.py`: Streamlit v1 with a sensitivity-aware add form, merged search results, measured latency, and a combined memory table showing sensitivity and sync status.
- `scripts/smoke_test_phase2.py`: exercises real mutable/immutable shards, including empty-immutable passthrough, overlap and distinct IDs, score order, deduplication, and combined memory listing.

What was run to verify it (commands + real output snippets):

1) ` .\.venv\Scripts\python.exe scripts\smoke_test_phase2.py`:

```text
EMPTY_IMMUTABLE_PASSTHROUGH=PASS mutable_hits=1 immutable_hits=0
DEDUP=PASS before=5 after=4 duplicates_removed=1
MERGE_ORDER=PASS top_k=10 latency_ms=9.98 duplicate_score=0.9053 best_source_score=0.9053
MEMORY_LIST=PASS listed=4 mutable=3 immutable=2
PHASE2_SMOKE_OK mutable=3 immutable=2 unique_results=4
```

2) ` .\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.headless true --server.port 8502`:

```text
Uvicorn server started on :::8502
Local URL: http://localhost:8502
```

Browser verification at `http://localhost:8502`: the dashboard loaded with add-memory and search forms. Added `Valve 8 pressure measured 39 psi during the field inspection.` and searched `valve 8 pressure field inspection`; the UI displayed a search latency of **8.03 ms** and rendered the memory/results tables after the Streamlit rerun completed.

Integration check with previous phases:
- In one PowerShell session, ran ` .\.venv\Scripts\python.exe scripts\smoke_test_phase1.py` followed by ` .\.venv\Scripts\python.exe scripts\smoke_test_phase2.py`; both passed unchanged/in sequence.
- Phase 1 output: `OFFLINE_SOCKET_GUARD=PASS blocked_attempts=0 OFFLINE=1`, all payload fields passed, and measured search times were 93.95 ms, 10.75 ms, and 7.63 ms (max 93.95 ms).
- Phase 2 output: `EMPTY_IMMUTABLE_PASSTHROUGH=PASS`, `DEDUP=PASS before=5 after=4 duplicates_removed=1`, `MEMORY_LIST=PASS listed=4 mutable=3 immutable=2`, and `PHASE2_SMOKE_OK`.
- Editor diagnostics reported no errors in the Phase 2 files.

Known issues / TODOs carried forward:
- Edge's WAL locks a shard for its owning process (`WouldBlock` when another process tries to load the same shard concurrently). Run only one process per device shard at a time; separate simulated devices continue to use separate shard directories.
- The Streamlit server is intentionally left running at `http://localhost:8502` for hands-on use. Stop it with Ctrl+C in its terminal when finished.

## Phase 3 — Real sync to server — 2026-09-27 19:52 +05:30

Status: PASS

What was built:
- `src/sync_worker.py`: in-memory upload queue, persisted `local_only` point recovery on worker runs, named-vector server collection creation, batched upsert, Qdrant partial-snapshot request using the immutable shard manifest, Edge snapshot restore, timestamp-filter purge, and start/stop background-thread helpers.
- `src/write_path.py`: every successful local insert now enters the upload queue after the Edge upsert.
- `scripts/smoke_test_phase3.py`: online end-to-end sync test and `--offline-branch`, which blocks socket connections and checks local search remains usable.
- Server collection choice: use the existing `QDRANT_COLLECTION=field_memories` setting (`.env.example`) rather than modifying the reference demo's `smart_glasses` collection. No collections or existing server points were deleted.
- Added post-purge verification and a bounded retry of the same timestamp cutoff filter: an integration run exposed one uploaded point surviving the first filter application; the retry now refuses to report success if uploaded IDs remain mutable.

What was run to verify it (commands + real output snippets):

1) `docker ps --filter "name=qdrant" --format "{{.Names}} {{.Status}} {{.Ports}}"`:

```text
qdrant Up 7 hours 0.0.0.0:6333->6333/tcp, [::]:6333->6333/tcp
```

2) ` .\.venv\Scripts\python.exe scripts\smoke_test_phase3.py` against the live Docker server:

```text
SERVER_POINT_COUNT before=7 after=9 uploaded=2
SHARDS before_mutable=2 after_mutable=0 immutable_after=9 restored=2
SYNC_STATUS server=synced immutable=synced queue_after=0
PARTIAL_SNAPSHOT=PASS bytes=198656 purged=2 cutoff=1790518919.765625
PHASE3_ONLINE_OK device_id=phase3-smoke-1cd046b2 points=2
```

The count includes earlier Phase 3 probe points; the test uses unique device IDs and leaves existing Qdrant data intact.

3) ` .\.venv\Scripts\python.exe scripts\smoke_test_phase3.py --offline-branch`:

```text
offline, skipping sync
OFFLINE_BRANCH=PASS blocked_attempts=0 local_hits=1 mutable=1 immutable=0 queued=1
PHASE3_OFFLINE_OK device_id=phase3-offline-8cf966c4
```

Integration check with previous phases:
- In one PowerShell session, ran `docker ps`, then Phase 1, Phase 2, Phase 3 online, and Phase 3 offline smoke tests in order; all passed.
- Phase 1 remained offline-safe: `OFFLINE_SOCKET_GUARD=PASS blocked_attempts=0 OFFLINE=1`; final search max was 97.00 ms.
- Phase 2 passed empty-immutable passthrough and merge/dedupe: `DEDUP=PASS before=5 after=4 duplicates_removed=1`; memory list was `listed=4 mutable=3 immutable=2`.
- Phase 3 online passed real server upsert, partial restore, and purge; offline passed with zero blocked socket attempts. Editor diagnostics reported no errors in Phase 3 files.

Known issues / TODOs carried forward:
- Edge WAL still permits only one process per device shard at a time; use separate device IDs/shard directories for concurrent simulated devices.
- The background worker is exposed through `start_sync_worker(device_id)`; smoke verification exercises `run_sync_once` to make results deterministic. There is not yet a dashboard sync control (dashboard sync log/toggle are Phase 5 work).
- `field_memories` accumulates smoke/probe points on the local Qdrant server so tests avoid destructive cleanup. Use a fresh local server or an explicitly approved cleanup before a presentation if a clean collection is required.

### Phase 3 follow-up — dashboard worker wiring — 2026-09-27 19:53 +05:30

- Wired the long-running Streamlit process to start one background worker for its selected device; `OFFLINE=1` continues to short-circuit all network access.
- Browser reload at `http://localhost:8502` completed without a runtime error. The previously added device-a note was then retrieved from Qdrant with `sync_status="synced"`:

```text
DASHBOARD_WORKER_SERVER_COUNT 10
DASHBOARD_WORKER_POINT [('ed103050-cfc2-413b-a9e3-a7de4afda12f', {'text': 'Valve 8 pressure measured 39 psi during the field inspection.', 'device_id': 'device-a', 'timestamp': 1790515138.6104856, 'access_count': 0, 'last_accessed': 1790515138.6104856, 'size_bytes': 61, 'sensitivity': 'low', 'sync_status': 'synced'})]
```

- This validates the dashboard-started worker against the live server, in addition to the sequential Phase 1–3 smoke tests above. Diagnostics report no errors in `dashboard/app.py`, `src/sync_worker.py`, or `src/write_path.py`.
