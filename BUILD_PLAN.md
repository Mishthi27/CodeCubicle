0. Non-negotiable rules for the agent

These apply across every phase. Repeat them to the agent if it drifts.

No phase skipping. Complete Phase N fully — including its verification checklist — before touching any Phase N+1 file. If Phase N verification fails, stay in Phase N and fix it.
Verify, don't assume. After every phase, the agent must actually run the code (not just read it) and paste real output — real latency numbers, real search results, real logs — into PROGRESS.md. "This should work" is not verification.
Integration check every phase, not just unit check. At the end of each phase, the agent must also re-run the smoke tests from all previous phases together in one process/session to confirm nothing regressed and that the pieces still talk to each other (e.g. Phase 3's sync must not break Phase 1's offline search; Phase 4's conflict logic must not break Phase 2's merge/dedupe). Write the result under an "Integration check" subsection in PROGRESS.md.
No silent mocking of the hard parts. Real local embeddings, a real Qdrant Edge shard, a real Qdrant server via Docker, real sync calls. Stubs are allowed ONLY as an explicitly labeled temporary placeholder in PROGRESS.md with a TODO and a reason, never presented as done.
Keep a living status log. Maintain PROGRESS.md at repo root, appended to (never overwritten) after every phase, in this format:
   ## Phase N — <name> — <date/time>
   Status: PASS / FAIL / PARTIAL
   What was built:
   What was run to verify it (commands + real output snippets):
   Integration check with previous phases:
   Known issues / TODOs carried forward:
Ask before destructive or ambiguous actions. If a step requires a decision not specified here (e.g. which embedding model file to download, which port to use), the agent should pick a sensible default, state it explicitly in PROGRESS.md, and proceed — but should ask the user before deleting data, force-pushing, or changing the scope.
One person, six days, working demo beats perfect code. Prefer the simplest implementation that satisfies the acceptance criteria. Do not gold-plate a phase before its criteria are met.
After each phase, STOP and report to the user with a short human-readable summary (2–5 sentences: what works, what was tested, what's next) before proceeding — even if not explicitly asked. Do not silently continue to the next phase in the same turn unless the user has approved the previous phase's verification.
1. Project context (for the agent's understanding)

We are building a solo hackathon project for Code Cubicle 6.0, Problem Statement 3 (Qdrant Edge): an offline-first "field memory assistant."

Timeline: 6 build days + 1 polish day. Online round 3 Oct, offline finale 11 Oct.
Core idea: A device stores memories (notes/observations) locally using Qdrant Edge (an in-process vector engine), searches them fully offline via local embeddings, and syncs to a central Qdrant server when connectivity returns — using Qdrant Edge's documented mutable/immutable dual-shard pattern. On top of Qdrant Edge (which does NOT provide this), we build our own differentiators: a sync-decision policy (rule-based, later a trained classifier) that decides what should sync vs. stay local, and conflict detection/resolution when two devices edit the same memory offline.
Reference implementation to clone first: github.com/qdrant/qdrant-edge-demo — the agent should clone and run this before writing any original code, to learn the real API surface, since Qdrant Edge is a new library and the agent's training data may be incomplete or stale on it.
Two "devices" are simulated as two local processes, each with its own shard directory and a --device-id flag — no real second machine needed.
Offline simulation is done via an OFFLINE=1 env var / flag that makes the sync worker skip network calls, not by physically unplugging anything (though that should also work if attempted live).
Data model (use this exactly, extend only if a phase needs it)

Memory point payload:

json
{
  "text": "Valve #3 pressure reading 42 psi",
  "device_id": "device-a",
  "timestamp": 1758700000.0,
  "access_count": 0,
  "last_accessed": 1758700000.0,
  "size_bytes": 512,
  "sensitivity": "low",
  "sync_status": "local_only"
}

Conflict record:

json
{
  "point_id": "p123",
  "local_version": {"device_id": "device-a", "timestamp": 1758700100, "text": "..."},
  "server_version": {"device_id": "device-b", "timestamp": 1758700180, "text": "..."},
  "resolution": "last_write_wins",
  "winner": "device-b"
}
Tech stack (defaults — agent may substitute only if something is genuinely broken, and must log why)
Piece	Choice
Edge vector store	qdrant-edge (Python)
Server	Qdrant server via local Docker (docker run qdrant/qdrant)
Embeddings	bge-small-en via ONNX Runtime, or fastembed (wraps this)
Local LLM (stretch)	llama.cpp + small GGUF model (Qwen2.5-1.5B-Instruct or Phi-3-mini)
Sync policy v1	Rule-based Python function
Sync policy v2	scikit-learn LogisticRegression or small MLP
Dashboard	Streamlit
Two devices	Two processes, separate shard dirs, --device-id flag
Offline simulation	OFFLINE=1 env var short-circuits sync worker's network calls
2. Repo structure (create this at Phase 0)
field-memory-assistant/
  BUILD_PLAN.md              <- this document, pasted in
  PROGRESS.md                <- living status log, append-only
  reference/qdrant-edge-demo/ <- cloned reference repo (read-only, do not edit)
  src/
    shard.py                  <- EdgeShard creation/wrapping (mutable + immutable)
    embeddings.py              <- local embedding wrapper
    write_path.py              <- insert flow: embed -> mutable shard -> policy -> queue
    read_path.py               <- query flow: query both shards -> merge/dedupe
    sync_worker.py              <- upload queue drain, partial snapshot pull, purge
    conflict.py                 <- conflict detection + LWW resolution
    policy_rules.py              <- rule-based sync policy
    policy_model.py               <- trained classifier, same interface as policy_rules
    llm.py                        <- optional local LLM answer generation
    device.py                      <- CLI entrypoint: `python -m src.device --device-id device-a`
  dashboard/
    app.py                          <- Streamlit dashboard
  scripts/
    simulate_usage_logs.py            <- synthetic data generator for training the policy
    smoke_test_phase1.py .. phaseN.py  <- one smoke test script per phase
  data/
    device-a/ device-b/                <- per-device shard directories (gitignored)
  requirements.txt
  .env.example
  README.md
3. Phases

Each phase below has: Objective, Tasks, Files touched, Acceptance criteria, Verification steps (run these, paste real output), Integration check.

Phase 0 — Environment & reference repo (budget: first ~1 hour of Day 1)

Objective: De-risk the newest, least-documented dependency (Qdrant Edge) before writing any original code.

Tasks:

Set up Python venv, requirements.txt with pinned versions of qdrant-edge, qdrant-client, fastembed (or onnxruntime + tokenizer), streamlit, scikit-learn, python-dotenv.
Clone github.com/qdrant/qdrant-edge-demo into reference/. Run its own demo end-to-end exactly as documented in its README.
Read through its source to confirm the real API for: EdgeShard.create(path, EdgeConfig(...)), named vectors, distance metric config, the upload_queue pattern, the partial snapshot endpoint (/collections/{name}/shards/0/snapshot/partial/create), update_from_snapshot, and the timestamp-based purge of duplicated points from the mutable shard.
Note in PROGRESS.md any place where the real API differs from this document's description — this document may be slightly stale since Qdrant Edge is new.
Stand up Qdrant server via Docker (docker run -p 6333:6333 qdrant/qdrant) and confirm it responds on localhost:6333.

Files touched: requirements.txt, .env.example, reference/, README.md (setup instructions).

Acceptance criteria:

Reference demo runs successfully with no errors.
Docker Qdrant server responds to a basic GET /collections.
Agent can state, in its own words in PROGRESS.md, the exact method signatures it will use in Phase 1 for shard creation and insertion.

Verification steps (agent must actually run and paste output):

bash
python reference/qdrant-edge-demo/<their entrypoint>   # paste real stdout
curl http://localhost:6333/collections                  # paste real JSON response

Integration check: N/A (first phase) — but confirm venv + Docker + reference repo all work together in one terminal session before proceeding.

Phase 1 — Mutable shard + local embeddings + offline search (Day 1)

Objective: A single device can insert and search memories fully offline, with real embeddings, zero network calls.

Tasks:

src/embeddings.py: wrap bge-small-en (via fastembed or ONNX) behind a simple embed(text: str) -> list[float] function. Confirm vector dimension matches what you'll configure in the shard.
src/shard.py: create a mutable EdgeShard at data/<device-id>/mutable/ with the named vector + distance metric matching the embedder's output.
src/write_path.py: function insert_memory(text, device_id, sensitivity="low") -> point_id that embeds text, builds the payload per the data model above (including timestamp, access_count=0, size_bytes=len(text.encode()), sync_status="local_only"), and writes to the mutable shard.
src/read_path.py: function search(query, top_k=5) -> list[dict] that embeds the query and searches the mutable shard only (immutable shard comes in Phase 2). Measure and log wall-clock latency for every search call — this number is needed for the demo later.
src/device.py: minimal CLI — insert a memory from stdin, run a search from stdin, print results with latency.
scripts/smoke_test_phase1.py: script that inserts N sample memories, runs a handful of queries, asserts results are returned, asserts no network call was attempted (e.g. by running with network disabled or by asserting no exception when offline), and prints latency stats.

Files touched: src/embeddings.py, src/shard.py, src/write_path.py, src/read_path.py, src/device.py, scripts/smoke_test_phase1.py.

Acceptance criteria:

Insert + search work with the machine's network interface disabled (or OFFLINE=1 set, even though the sync worker doesn't exist yet — the point is no code path in this phase touches the network).
Search latency is sub-second for a small number of points (log the actual number, don't estimate it).
Payload contains every field from the data model.

Verification steps:

bash
python scripts/smoke_test_phase1.py     # paste real stdout including latency numbers
# also literally try: turn off wifi / unplug ethernet, rerun, confirm identical behavior

Integration check: None yet (only phase built) — but explicitly note in PROGRESS.md that this phase's shard directory layout (data/<device-id>/mutable/) is what Phase 2 will build on, so it isn't accidentally renamed later.

Phase 2 — Immutable shard + merge/dedupe + dashboard v1 (Day 2)

Objective: Introduce the second shard (empty for now) and a unified read path that merges both; get a visible UI running.

Tasks:

src/shard.py: add creation of an immutable EdgeShard at data/<device-id>/immutable/, same vector config as the mutable one.
src/read_path.py: extend search() to query both shards, merge results by score, and dedupe by point ID (for now, since the immutable shard is empty, this should be a no-op passthrough — verify that explicitly).
dashboard/app.py: Streamlit v1 with:
Add-memory form (text + sensitivity dropdown).
Search box, results list, latency shown on screen.
List of memories with their sync_status.
scripts/smoke_test_phase2.py: insert into mutable, manually insert a couple of synthetic points directly into the immutable shard (simulating "already synced" points) with overlapping and non-overlapping IDs, and assert the merged/deduped search returns the correct deduplicated set.

Files touched: src/shard.py, src/read_path.py, dashboard/app.py, scripts/smoke_test_phase2.py.

Acceptance criteria:

Merge+dedupe logic is provably correct: a point ID present in both shards appears exactly once in results.
Dashboard loads, add-memory and search both work through the UI (not just CLI).
Latency still shown and still fast.

Verification steps:

bash
python scripts/smoke_test_phase2.py     # paste real output showing dedup counts before/after
streamlit run dashboard/app.py          # manually confirm in browser: add a memory, search for it, screenshot or describe what's shown

Integration check: Re-run scripts/smoke_test_phase1.py unchanged and confirm it still passes (offline single-shard search behavior must be unaffected by the new dual-shard merge code path when the immutable shard is empty).

Phase 3 — Real sync to server (Day 3)

Objective: Writes actually leave the device and come back, following Qdrant Edge's documented sync pattern.

Tasks:

Confirm Docker Qdrant server is running; create the server-side collection matching the shard's vector config.
src/sync_worker.py:
Upload queue: every write in write_path.py also appends to an in-memory upload_queue.
Background worker (thread or asyncio loop) that batches queued points and upserts them to the server via qdrant_client, then updates their local sync_status to "synced".
Partial snapshot pull: request /collections/{name}/shards/0/snapshot/partial/create, restore into the immutable shard via update_from_snapshot.
Purge step: delete now-duplicated points from the mutable shard using the timestamp payload field as the cutoff, exactly per the documented pattern.
Add OFFLINE env var / CLI flag: when set, sync_worker.py must skip all network calls entirely (not fail — skip cleanly and log "offline, skipping sync").
scripts/smoke_test_phase3.py: with server up and OFFLINE unset — insert memories, run the sync worker once, confirm points appear server-side (query the server directly to check), confirm partial snapshot restores into immutable shard, confirm purge removes the now-duplicated points from mutable. Then flip OFFLINE=1, insert more memories, confirm sync worker does nothing and no exception is raised, confirm local search still works.

Files touched: src/sync_worker.py, src/write_path.py (queue hook), scripts/smoke_test_phase3.py, .env.example (OFFLINE var).

Acceptance criteria:

End-to-end: insert on device → appears on Qdrant server → appears in local immutable shard → removed from local mutable shard (no duplication).
OFFLINE=1 fully prevents any network call — verify by running with network disabled and confirming no error, not just by reading the code.
sync_status field accurately reflects state at every point (local_only → synced).

Verification steps:

bash
docker ps                                 # confirm qdrant server container running
python scripts/smoke_test_phase3.py       # paste real output: server point counts, before/after shard contents
OFFLINE=1 python scripts/smoke_test_phase3.py --offline-branch   # paste output showing clean skip

Integration check: Re-run Phase 1 and Phase 2 smoke tests. Confirm offline search (Phase 1 behavior) is unaffected when OFFLINE=1, and confirm merge/dedupe (Phase 2 logic) correctly reflects the new state after a real sync (not just the synthetic points used in Phase 2's test).

Phase 4 — Conflict handling + rule-based sync policy (Day 4)

Objective: Two devices editing the same memory offline produces a detectable, explainable conflict; every write is scored by a policy that decides local-only vs. sync.

Tasks:

Confirm every write already carries device_id and timestamp (from Phase 1) — extend if any gaps found.
src/conflict.py:
Detection: during merge (Phase 2's read path) or during sync (Phase 3's pull), flag when the same point ID (or near-duplicate embedding above a similarity threshold — pick and log a threshold, e.g. cosine ≥ 0.95) appears with differing text content across shards/devices.
Resolution: last-write-wins by timestamp (tie-break by device_id string comparison, log this choice).
Emit a ConflictRecord (per the data model above) into a conflict log (simple JSON-lines file or a dedicated collection — agent's choice, log it).
src/policy_rules.py: pure function decide(payload, novelty_score) -> ("sync"|"keep_local", confidence, reason_string) using thresholds on: recency (now - timestamp), access_count, novelty (max cosine similarity to existing server-known points — low similarity = novel = more likely to sync), size_bytes, sensitivity (high sensitivity biases toward keep_local). Wire this into write_path.py so every insert is scored and sync_status is set to "local_only" or queued accordingly, instead of always syncing.
scripts/smoke_test_phase4.py:
Simulate two devices writing to the same point ID with different text and different timestamps offline, then sync both, confirm the later timestamp wins and a ConflictRecord is created with the correct winner.
Feed the rule-based policy a spread of synthetic payloads (varying recency/access/novelty/size/sensitivity) and confirm decisions and reasons look sane (e.g. high-sensitivity + low novelty → keep_local).

Files touched: src/conflict.py, src/policy_rules.py, src/write_path.py (policy hook), scripts/smoke_test_phase4.py.

Acceptance criteria:

A real two-device conflict (not just a unit-test mock) is produced, detected, and resolved with a clear, inspectable reason.
The rule-based policy is now actually gating sync decisions in write_path.py — Phase 3's "always sync everything" behavior is replaced by policy-gated sync.
Policy decisions are explainable in one line (shown later in the dashboard).

Verification steps:

bash
python scripts/smoke_test_phase4.py     # paste real ConflictRecord JSON and a table of policy decisions with reasons

Integration check: Re-run Phase 3's sync smoke test — confirm points now sync selectively (per the policy) rather than unconditionally, and that this doesn't break the upload-queue/partial-snapshot/purge pipeline. Re-run Phase 2's merge/dedupe test and confirm conflicting points are now flagged rather than silently overwritten.

Phase 5 — Trained sync policy + dashboard polish (Day 5)

Objective: Swap the rule-based policy for a trained classifier behind the same interface; finish the dashboard.

Tasks:

scripts/simulate_usage_logs.py: generate synthetic memories with varied recency/access_count/novelty/size/sensitivity, labeled using the Phase 4 rule-based policy (or a hand-labeled subset for realism) — save as a CSV/JSON training set.
src/policy_model.py: train LogisticRegression (or a small MLP via scikit-learn MLPClassifier) on those features, exposing the same decide(payload, novelty_score) -> (decision, confidence, reason) interface as policy_rules.py. Save accuracy/precision/recall to a metrics file — this is going on a slide, so it must be a real computed number, not invented.
Swap write_path.py to use policy_model.py by default, with a config flag to fall back to policy_rules.py (keep the rule-based version as the demo-day fallback per the original risk plan).
Dashboard polish in dashboard/app.py:
Sync log view (uploads, snapshot pulls, purges).
Conflict viewer (list of ConflictRecords, local vs server version, winner, reason).
Online/offline toggle wired to the real OFFLINE flag.
Per-shard memory counts (mutable vs immutable, per device).
scripts/smoke_test_phase5.py: run the trained policy on a held-out slice of the synthetic data, print real accuracy/precision/recall, and confirm the dashboard's new views render with real data (screenshots or described output).

Files touched: scripts/simulate_usage_logs.py, src/policy_model.py, src/write_path.py (policy swap), dashboard/app.py, scripts/smoke_test_phase5.py.

Acceptance criteria:

Real accuracy/precision/recall numbers exist and are saved somewhere reusable for the demo slide.
Switching between rule-based and trained policy is a one-line config change, not a rewrite.
Dashboard shows sync log, conflicts, toggle, and counts, all backed by real data from Phases 1–4.

Verification steps:

bash
python scripts/simulate_usage_logs.py         # paste sample of generated data
python scripts/smoke_test_phase5.py           # paste real accuracy/precision/recall
streamlit run dashboard/app.py                # confirm all four new views manually, describe what you see

Integration check: Run the full pipeline once with the trained policy active: insert on two simulated devices, go offline, create a conflict, come back online, sync, and confirm the dashboard's sync log + conflict viewer accurately reflect everything that happened in Phases 1–4's machinery. This is the first "everything together" run — treat any mismatch as a blocking bug, not a polish item.

Phase 6 — Local LLM (stretch) + two-device demo run (Day 6)

Objective: Optional answer-from-memory feature, and a rehearsed two-device offline/online demo.

Tasks (only if Phases 1–5 are genuinely done and verified — do not start this while earlier phases are PARTIAL):

src/llm.py: wire up llama.cpp with a small GGUF model (Qwen2.5-1.5B-Instruct or Phi-3-mini). Function answer(query, retrieved_memories) -> str that stuffs top-k retrieved memories into a short prompt and generates locally, no API calls.
Wire an "Ask" mode into the dashboard: user question → merged search (Phase 2/3 read path) → top-k into llm.py → displayed answer with the source memories shown alongside it.
Run two src/device.py processes side by side (--device-id device-a, --device-id device-b), each with OFFLINE=1, both editing the same memory, then flip both to online and run the sync worker, confirming the full pipeline end-to-end at least twice in a row.
scripts/smoke_test_phase6.py: automate the two-device conflict-then-sync scenario end-to-end as a single script (no manual steps), so it can be re-run on demand before the actual demo.

Files touched: src/llm.py, dashboard/app.py (Ask mode), scripts/smoke_test_phase6.py.

Acceptance criteria:

If included: local LLM answers are generated with zero network calls, using only locally retrieved memories, and this is verified with the network disabled.
The two-device scenario runs successfully twice in a row via a single script, with no manual intervention required.

Verification steps:

bash
python scripts/smoke_test_phase6.py    # run twice, paste both real outputs

Integration check: This IS the integration check — Phase 6's script exercises Phases 1 through 5 together as the real demo will. Any flakiness here must be fixed before Phase 7, since this script becomes the rehearsal script.

Phase 7 — Polish, demo script, backup video (last day)

Objective: De-risk the live demo.

Tasks:

Fix any rough edges surfaced by Phase 6's repeated runs.
Rehearse the demo script (hook → offline search → conflicting edits → reconnect/sync log → policy-in-action table → metrics slide → close), timing each section.
Record a backup video of the full demo (including the live network-cut moment) in case live manipulation misbehaves on stage.
Prepare the metrics slide with real numbers pulled from PROGRESS.md: offline query latency (Phase 1), policy classifier accuracy/precision/recall (Phase 5), sync round-trip time (Phase 3/6).
Final full run-through of scripts/smoke_test_phase6.py (or a renamed scripts/full_demo_dryrun.py) as the last verification.

Acceptance criteria (Definition of Done):

Search works with the network fully off, latency shown on screen.
Writes sync to the server and back via partial snapshot, following the documented pattern.
Two devices can edit the same memory offline; reconnecting shows a clear, explained resolution.
A working sync-decision policy (rule-based at minimum, trained as achieved) with visible reasoning.
Dashboard shows memory, search, sync log, and conflicts.
Backup demo video recorded.

Verification steps: Full dry run of the demo script end-to-end, timed, with a human (the user) watching and confirming each beat lands.

Integration check: This is the final, whole-system check — every phase's smoke test plus the live demo script must all pass in the same session immediately before presenting.

4. Risk/fallback table (keep visible to the agent throughout)
Risk	Fallback
qdrant-edge package has rough edges (it's new)	Phase 0 budgets the first hour purely to running the official demo repo before writing original code
Partial-snapshot sync is fiddly	Fall back to full-snapshot resync for the demo if partial sync misbehaves under time pressure; mention partial sync as the "production" path
No time for a trained policy model	Ship the rule-based policy (Phase 4) — it still satisfies "dynamically decide"; say the trained version is next on the roadmap
Local LLM too slow/heavy	Cut Phase 6's LLM piece; retrieval + a clean answer template is still a complete story
Live network-cut demo fails on stage	Backup video recorded in advance (Phase 7); keep the OFFLINE flag as a guaranteed manual trigger instead of physically unplugging anything
