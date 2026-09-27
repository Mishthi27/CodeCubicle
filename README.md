# Field Memory Assistant (Code Cubicle 6.0 — Qdrant Edge)

Offline-first notes/observations stored in Qdrant Edge, searchable with local embeddings, and synced to a central Qdrant server when connectivity returns.

## Setup (Phase 0)

Requires **Python 3.11** (not 3.14 — the official Edge demo pins `>=3.11,<3.14`) and **Docker Desktop**.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

Confirm the server:

```powershell
curl.exe http://localhost:6333/collections
```

### Official reference demo

```powershell
git clone --depth 1 https://github.com/qdrant/qdrant-edge-demo.git reference/qdrant-edge-demo
# Install uv (https://docs.astral.sh/uv/) then, from that directory:
uv sync
uv run python -c "from fastembed import ImageEmbedding, TextEmbedding; ImageEmbedding(model_name='Qdrant/clip-ViT-B-32-vision', cache_dir='./models'); TextEmbedding(model_name='Qdrant/clip-ViT-B-32-text', cache_dir='./models')"
uv run uvicorn backend.server:app --port 8000
# another terminal:
uv run streamlit run app.py
```

Windows has no `make`; the commands above are the Makefile `setup` / `backend` / `demo` targets.

See `BUILD_PLAN.md` for phases and `PROGRESS.md` for verification logs.

### Train the sync policy (Phase 5)

The trained policy is the default (`SYNC_POLICY=model`). Generate its labeled dataset and save the model/held-out metrics before starting the dashboard:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_usage_logs.py
.\.venv\Scripts\python.exe -m src.policy_model
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```

The model, dataset, and metrics are stored under the ignored `data/` directory. Set `SYNC_POLICY=rules` in `.env` to use the Phase 4 fallback.

### Phase 6 Ask mode

Ask retrieves local memories and builds a short answer from their text. The optional llama.cpp/GGUF backend was not enabled in this environment because no local model/runtime was cached and pip could not resolve a Windows `llama-cpp-python` wheel; the grounded retrieval answer is the documented fallback. The two-device rehearsal is available as:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test_phase6.py
```

## Defaults chosen in Phase 0

| Item | Choice |
| --- | --- |
| Python | 3.11.9 |
| Edge package | `qdrant-edge-py==0.8.0` (import `qdrant_edge`) |
| Qdrant server | Docker `qdrant/qdrant` on port **6333** |
| Embeddings (from Phase 1) | `fastembed` + bge-small-en |
| Repo layout | this repository root (not a nested `field-memory-assistant/` folder) |
