import os
import json
import time
from pathlib import Path

import streamlit as st

from src.conflict import read_conflicts
from src.llm import answer
from src.read_path import list_memories, search, shard_counts
from src.sync_worker import read_sync_log, start_sync_worker, stop_sync_worker
from src.write_path import insert_memory


st.set_page_config(page_title="Field Memory", layout="wide")
st.title("Field Memory")
st.caption("Local memories · offline search")

device_id = st.sidebar.text_input(
    "Device ID",
    value=os.getenv("DEVICE_ID", "device-a"),
).strip()

if "offline_mode" not in st.session_state:
    st.session_state["offline_mode"] = (
        os.getenv("OFFLINE", "0").strip().lower() in {"1", "true", "yes", "on"}
    )


def _apply_offline_setting() -> None:
    os.environ["OFFLINE"] = "1" if st.session_state["offline_mode"] else "0"


st.sidebar.toggle(
    "Offline",
    key="offline_mode",
    on_change=_apply_offline_setting,
    help="When enabled, the sync worker makes no network calls.",
)
_apply_offline_setting()
policy_name = os.getenv("SYNC_POLICY", "model").strip().lower()
st.sidebar.caption(f"Sync policy: {policy_name}")

if not device_id:
    st.error("Enter a device ID to continue.")
    st.stop()

previous_worker_device = st.session_state.get("sync_worker_device")
if previous_worker_device and previous_worker_device != device_id:
    stop_sync_worker(previous_worker_device)
start_sync_worker(device_id)
st.session_state["sync_worker_device"] = device_id

add_column, search_column = st.columns([0.9, 1.1], gap="large")

with add_column:
    st.subheader("Add memory")
    with st.form("add_memory_form", clear_on_submit=True):
        memory_text = st.text_area("Memory", placeholder="Record a field observation")
        sensitivity = st.selectbox(
            "Sensitivity",
            options=("low", "medium", "high"),
            index=0,
        )
        add_submitted = st.form_submit_button("Add memory", icon=":material/add:")

    if add_submitted:
        if not memory_text.strip():
            st.error("Memory text cannot be empty.")
        else:
            try:
                point_id = insert_memory(memory_text, device_id, sensitivity)
                st.success(f"Saved locally · {point_id}")
            except Exception as error:
                st.error(f"Could not save memory: {error}")

with search_column:
    st.subheader("Search")
    with st.form("search_form"):
        query_text = st.text_input(
            "Search memories",
            placeholder="e.g. pressure readings",
        )
        top_k = st.number_input("Results", min_value=1, max_value=20, value=5)
        search_submitted = st.form_submit_button(
            "Search memories",
            icon=":material/search:",
        )

    if search_submitted:
        if not query_text.strip():
            st.error("Enter a search query.")
        else:
            try:
                started = time.perf_counter()
                st.session_state["search_results"] = search(
                    query_text,
                    top_k=int(top_k),
                    device_id=device_id,
                )
                st.session_state["search_latency_ms"] = (
                    time.perf_counter() - started
                ) * 1000
            except Exception as error:
                st.error(f"Search failed: {error}")

    if "search_results" in st.session_state:
        st.metric("Search latency", f"{st.session_state['search_latency_ms']:.2f} ms")
        results = st.session_state["search_results"]
        if results:
            st.dataframe(
                [
                    {
                        "Score": round(result["score"], 4),
                        "Memory": result["payload"].get("text", ""),
                        "Status": result["payload"].get("sync_status", "unknown"),
                        "Decision": result["payload"].get("sync_decision", ""),
                    }
                    for result in results
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No matching memories.")

st.divider()
st.subheader("Ask")
with st.form("ask_form"):
    question = st.text_input("Question", placeholder="Ask about a field observation")
    ask_submitted = st.form_submit_button("Ask memories", icon=":material/chat:")

if ask_submitted:
    if not question.strip():
        st.error("Enter a question.")
    else:
        try:
            st.session_state["ask_sources"] = search(
                question,
                top_k=3,
                device_id=device_id,
            )
            st.session_state["ask_answer"] = answer(
                question,
                st.session_state["ask_sources"],
            )
        except Exception as error:
            st.error(f"Could not answer from local memories: {error}")

if "ask_answer" in st.session_state:
    st.markdown(st.session_state["ask_answer"])
    sources = st.session_state["ask_sources"]
    if sources:
        st.caption("Source memories")
        st.dataframe(
            [
                {
                    "Memory": source["payload"].get("text", ""),
                    "Score": round(source["score"], 4),
                    "Device": source["payload"].get("device_id", ""),
                }
                for source in sources
            ],
            hide_index=True,
            width="stretch",
        )

st.divider()
st.subheader("Memories")

try:
    memories = list_memories(device_id)
    if memories:
        st.dataframe(
            [
                {
                    "Memory": item["payload"].get("text", ""),
                    "Sensitivity": item["payload"].get("sensitivity", ""),
                    "Sync status": item["payload"].get("sync_status", "unknown"),
                    "Policy": item["payload"].get("sync_decision", ""),
                    "Reason": item["payload"].get("sync_reason", ""),
                    "Updated": time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(item["payload"].get("timestamp", 0)),
                    ),
                }
                for item in memories
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No memories stored on this device yet.")
except Exception as error:
    st.error(f"Could not load memories: {error}")

st.divider()
st.subheader("Sync activity")
device_ids = list(dict.fromkeys(("device-a", "device-b", device_id)))
counts_by_device = []
for current_device in device_ids:
    try:
        counts = shard_counts(current_device)
        counts_by_device.append(
            {
                "Device": current_device,
                "Mutable": counts["mutable"],
                "Immutable": counts["immutable"],
                "Total": counts["mutable"] + counts["immutable"],
            }
        )
    except Exception as error:
        st.error(f"Could not count shards for {current_device}: {error}")

if counts_by_device:
    st.dataframe(counts_by_device, hide_index=True, width="stretch")

metrics_path = Path(__file__).resolve().parents[1] / "data" / "policy_metrics.json"
if metrics_path.exists():
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        metric_columns = st.columns(3)
        metric_columns[0].metric("Held-out accuracy", f"{metrics['accuracy']:.1%}")
        metric_columns[1].metric("Sync precision", f"{metrics['sync_precision']:.1%}")
        metric_columns[2].metric("Sync recall", f"{metrics['sync_recall']:.1%}")
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        st.error(f"Could not load policy metrics: {error}")

sync_entries = read_sync_log(limit=50)
if sync_entries:
    st.dataframe(
        [
            {
                "Time": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(entry["timestamp"]),
                ),
                "Device": entry.get("device_id", ""),
                "Event": entry.get("event", ""),
                "Uploaded": entry.get("uploaded", 0),
                "Snapshot bytes": entry.get("snapshot_bytes", 0),
                "Purged": entry.get("purged", 0),
                "Conflicts": len(entry.get("conflicts", [])),
            }
            for entry in sync_entries
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("No sync activity recorded yet.")

st.subheader("Conflicts")
conflicts = read_conflicts()
if conflicts:
    st.dataframe(
        [
            {
                "Point ID": conflict["point_id"],
                "Local device": conflict["local_version"]["device_id"],
                "Server device": conflict["server_version"]["device_id"],
                "Winner": conflict["winner"],
                "Resolution": conflict["reason"],
            }
            for conflict in reversed(conflicts[-50:])
        ],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Inspect conflict versions"):
        for conflict in reversed(conflicts[-20:]):
            st.markdown(f"**{conflict['point_id']} · winner: {conflict['winner']}**")
            st.json(
                {
                    "local_version": conflict["local_version"],
                    "server_version": conflict["server_version"],
                    "resolution": conflict["resolution"],
                    "reason": conflict["reason"],
                }
            )
else:
    st.info("No conflicts recorded.")