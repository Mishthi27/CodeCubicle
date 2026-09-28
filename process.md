# Field Memory Operator Process

This is the hands-on guide for starting, exploring, and rehearsing the Field Memory assistant. The system stores vectors locally with Qdrant Edge, searches on-device, and syncs selected notes to the local Qdrant server when online.

## 1. Start the environment

Open PowerShell at the repository root. Start Docker Desktop, then start Qdrant if the container is not already running:

```powershell
docker ps --filter "name=qdrant"
# If it is not running:
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

Confirm the server responds:

```powershell
Invoke-RestMethod http://localhost:6333/collections
```

Use Python 3.11 and the repository environment. The BGE embedding model and the trained policy must already be cached/generated before the first offline demo:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_usage_logs.py
.\.venv\Scripts\python.exe -m src.policy_model
```

This writes the policy dataset, model, and computed metrics below `data/`.

## 2. Start the dashboard

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.headless true --server.port 8502
```

Open `http://localhost:8502`. The dashboard starts the sync worker for the selected device. Keep only one process open per device shard: Qdrant Edge's WAL locks each shard to its owning process. Use distinct device IDs when running multiple devices.

The sidebar contains:

- **Device ID**: local shard owner, normally `device-a`.
- **Offline**: when enabled, the worker records a skip and makes no server calls.
- **Sync policy**: `model` by default; set `SYNC_POLICY=rules` in `.env` to use the Phase 4 fallback.

## 3. Capture a field note

In **Field desk**, enter an observation, choose its sensitivity, and select **Save note**. The note is embedded locally, assigned a UUID, stored in the device's mutable shard, and scored by the selected sync policy. The stored row shows sync state, decision, and reason.

High-sensitivity or otherwise policy-rejected notes remain `local_only`; they are not put on the upload queue. Do not describe `local_only` as a failed sync: it can be the intentional policy result.

## 4. Search and Ask offline

1. Turn **Offline** on in the sidebar.
2. In **Search field notes**, enter a query and select **Search offline**. Check the result, score, sync state, and measured latency.
3. In **Ask from your notes**, enter a question. The response is grounded in retrieved local notes; source notes appear below it.
4. Turn **Offline** off when ready to sync.

The local GGUF/llama.cpp runtime was unavailable in this environment. Ask therefore uses the documented retrieval-plus-answer-template fallback. It is not an LLM-generated answer.

## 5. Inspect sync and policy

Use the dashboard tabs:

- **Sync log**: compare mutable and immutable counts per device and inspect upload, partial-snapshot, purge, offline-skip, and conflict events.
- **Conflicts**: inspect local/server text, timestamps, winner, and the last-write-wins reason.
- **Policy & metrics**: review per-memory reasons and held-out metrics. Metrics are computed against synthetic labels produced by the Phase 4 rules; they measure rule imitation, not independently labeled real-world quality.

## 6. Rehearse the two-device conflict

The repeatable rehearsal uses real separate CLI processes, unique shard directories, real local embeddings, and the live Qdrant server. It performs two offline-write/online-sync conflict rounds per invocation:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test_phase6.py
```

Each round creates a shared UUID on `device-a-phase6-*` and `device-b-phase6-*`, writes different text while offline, verifies the note is locally searchable, then syncs both. The later timestamp should win and a ConflictRecord should appear in the log/viewer. These unique device suffixes avoid contending with the dashboard's open `device-a` shard.

For the full set of phase gates in order:

```powershell
.\.venv\Scripts\python.exe scripts\full_demo_dryrun.py
```

This runs the Phase 1 through Phase 6 smoke tests, including the Phase 3 offline branch. The command exits on the first failure and prints per-step elapsed time. For the final presentation rehearsal, run it with the dashboard open and have a human watch the screen; the script does not replace that live confirmation.

## 7. Demo sequence

Use this order for a short live walkthrough:

1. Start at **Field desk** and show the active device and sync policy.
2. Turn **Offline** on. Save a field observation and search for it. Point out that the result is local and latency is visible.
3. Use **Ask from your notes** and show the cited source note.
4. Run the two-device conflict rehearsal. Explain that the same UUID received different offline text and the later timestamp won after reconnect.
5. Open **Conflicts** to show both versions and the reason; open **Sync log** to show uploads, snapshot restore, purge, and shard counts.
6. Open **Policy & metrics**. Explain that high-sensitivity or similar memories can remain local, and state that the model metrics use synthetic rule-generated labels.
7. Close with the offline-first workflow and the server-backed sync path.

## 8. Backup video

The Streamlit **Record screen** action was tested, but the integrated browser reported `ScreenCastRecorder.initialize error: NotSupportedError`; no backup video was produced in this environment. Before presenting, record the walkthrough above with OBS Studio or Windows Xbox Game Bar (Win+Alt+R, if enabled). Include the Offline toggle, local search, both device edits, reconnection, conflict resolution, and sync log. Save the recording outside `data/` so it is not confused with application artifacts.

## 9. Troubleshooting

- `WouldBlock` or a WAL lock error: another process already owns that device's shard. Close that process or use a fresh device ID; do not delete the shard to clear the lock.
- Empty Ask/search results: confirm the selected device ID owns the notes, and that the model cache exists for the first-ever disconnected run.
- Sync does not start: check the Offline toggle, Docker status, and `QDRANT_URL` / `QDRANT_COLLECTION` in `.env`.
- Policy model missing: regenerate `data/policy_training.csv` and run `python -m src.policy_model`, or set `SYNC_POLICY=rules` as the fallback.
- Conflict winner: compare timestamps first; exact ties are resolved by lexicographically greater `device_id`.
