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
