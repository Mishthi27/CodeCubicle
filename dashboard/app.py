import html
import json
import os
import time
from pathlib import Path

import streamlit as st

from src.conflict import read_conflicts
from src.llm import answer
from src.read_path import list_memories, search, shard_counts
from src.sync_worker import read_sync_log, start_sync_worker, stop_sync_worker
from src.write_path import insert_memory


st.set_page_config(page_title="Field Memory", page_icon="FM", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --paper: #eeece3;
        --ink: #182722;
        --muted: #68746c;
        --line: #d2d1c4;
        --forest: #17352d;
        --forest-soft: #315b49;
        --signal: #e06f43;
        --signal-soft: #f4dfd2;
        --white: #fbfaf5;
        --moss: #a6b597;
        --grid: rgba(23, 53, 45, 0.065);
    }
    .stApp {
        color: var(--ink);
        background-color: var(--paper);
        background-image:
            linear-gradient(90deg, transparent 97%, var(--grid) 98%),
            linear-gradient(0deg, transparent 97%, var(--grid) 98%);
        background-size: 34px 34px;
    }
    [data-testid="stHeader"] { background: rgba(238, 236, 227, 0.94); }
    [data-testid="stAppViewContainer"] > .main .block-container {
        max-width: 1440px;
        padding-top: 0.8rem;
        padding-bottom: 2.5rem;
    }
    [data-testid="stSidebar"] {
        background: var(--forest);
        border-right: 1px solid #305447;
    }
    [data-testid="stSidebar"] * { color: #eff4ed; }
    [data-testid="stSidebar"] input { color: var(--ink); }
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #cad8cf;
    }
    .fm-rail-mark {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 42px;
        height: 42px;
        margin: 0.2rem 0 1rem;
        border: 1px solid #9ead94;
        border-radius: 50%;
        color: #f7f2e5;
        font: 700 12px/1 Consolas, monospace;
    }
    .fm-header {
        position: relative;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1.5rem;
        min-height: 148px;
        margin: 0.15rem 0 0;
        padding: 1.25rem 1.65rem;
        border: 1px solid #315347;
        border-radius: 5px 5px 0 0;
        background-color: var(--forest);
        background-image:
            repeating-radial-gradient(ellipse at 84% 42%, transparent 0 19px, rgba(213, 224, 199, 0.13) 20px 21px, transparent 22px 39px),
            linear-gradient(118deg, transparent 54%, rgba(166, 181, 151, 0.09) 54.2%, transparent 54.6%);
        color: #f7f2e5;
    }
    .fm-eyebrow {
        margin: 0 0 0.45rem;
        color: #c4d0b5;
        font: 700 10px/1.3 Consolas, monospace;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    .fm-title {
        margin: 0;
        color: #fbf7ec;
        font: 400 43px/1.02 Georgia, 'Times New Roman', serif;
        letter-spacing: 0;
    }
    .fm-header-note {
        z-index: 1;
        min-width: 190px;
        padding: 0.75rem 0 0.75rem 1rem;
        border-left: 2px solid var(--signal);
        color: #e3e8d8;
        font: 600 11px/1.7 Consolas, monospace;
        text-align: right;
    }
    .fm-status-strip {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.75rem 1.4rem;
        margin: 0 0 1.15rem;
        padding: 0.65rem 1rem;
        border: 1px solid var(--line);
        border-top: 0;
        border-radius: 0 0 5px 5px;
        background: rgba(251, 250, 245, 0.92);
        color: var(--muted);
        font: 600 10px/1.35 Consolas, monospace;
        text-transform: uppercase;
    }
    .fm-status-strip strong { color: var(--ink); }
    .fm-status-live { color: #276746; }
    .fm-status-offline { color: #b44828; }
    .fm-tab-note {
        margin: 0.1rem 0 1rem;
        color: var(--muted);
        font: 400 13px/1.5 Georgia, serif;
    }
    .fm-section-label {
        margin: 1.3rem 0 0.55rem;
        color: var(--forest-soft);
        font: 700 10px/1.2 Consolas, monospace;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    h1, h2, h3 { color: var(--forest); }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.3rem;
        padding: 0.35rem;
        border: 1px solid #c9cdc0;
        border-radius: 5px;
        background: #e3e4d9;
    }
    [data-testid="stTabs"] button[role="tab"] {
        height: 2.45rem;
        padding: 0 1rem;
        border-radius: 4px;
        color: #58665d;
        font: 700 11px/1 Consolas, monospace;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        background: var(--forest);
        color: #fbf7ec;
        box-shadow: inset 0 -2px var(--signal);
    }
    .stButton > button, [data-testid="stFormSubmitButton"] > button {
        min-height: 2.55rem;
        border: 1px solid var(--forest);
        border-radius: 4px;
        background: var(--forest);
        color: white;
        font: 700 12px Consolas, monospace;
    }
    .stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
        border-color: var(--forest-soft);
        background: var(--forest-soft);
        color: white;
    }
    [data-testid="stMetric"] {
        padding: 0.7rem 0.85rem;
        border: 1px solid var(--line);
        border-radius: 4px;
        background: var(--white);
    }
    [data-testid="stMetricLabel"] p {
        color: var(--muted);
        font: 700 10px/1.3 Consolas, monospace;
        text-transform: uppercase;
    }
    [data-testid="stMetricValue"] { color: var(--forest); }
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        border-radius: 4px;
        background: var(--white);
    }
    [data-testid="stForm"] {
        padding: 1rem;
        border: 1px solid #cfcec1;
        border-top: 2px solid var(--forest-soft);
        border-radius: 4px;
        background: var(--white);
        box-shadow: 0 4px 12px rgba(29, 48, 39, 0.035);
    }
    .fm-record-list { border-top: 1px solid var(--line); }
    .fm-record {
        display: grid;
        grid-template-columns: 44px minmax(0, 1fr) minmax(128px, 185px);
        gap: 0.75rem;
        align-items: center;
        padding: 0.82rem 0.55rem;
        border-bottom: 1px solid var(--line);
        background: rgba(251, 250, 245, 0.82);
    }
    .fm-record-index {
        align-self: start;
        padding-top: 0.1rem;
        color: #9a6a4b;
        font: 700 10px Consolas, monospace;
    }
    .fm-record-text {
        color: var(--ink);
        font: 400 15px/1.45 Georgia, serif;
        overflow-wrap: anywhere;
    }
    .fm-record-meta {
        display: flex;
        flex-wrap: wrap;
        justify-content: flex-end;
        gap: 0.3rem;
        color: var(--muted);
        font: 700 9px/1.3 Consolas, monospace;
        text-align: right;
        text-transform: uppercase;
    }
    .fm-tag {
        display: inline-block;
        padding: 0.25rem 0.4rem;
        border: 1px solid #c7d0c3;
        border-radius: 3px;
        background: #eef1e8;
        color: #315b49;
    }
    .fm-tag-signal {
        border-color: #e5b59d;
        background: var(--signal-soft);
        color: #93462d;
    }
    .fm-record-reason {
        grid-column: 2 / 4;
        margin-top: -0.4rem;
        color: var(--muted);
        font: 400 11px/1.45 Consolas, monospace;
        overflow-wrap: anywhere;
    }
    .fm-score { color: var(--signal); font: 700 11px Consolas, monospace; }
    .fm-sync-row {
        display: grid;
        grid-template-columns: 165px 1fr repeat(4, minmax(68px, 95px));
        gap: 0.6rem;
        align-items: center;
        padding: 0.7rem 0.55rem;
        border-bottom: 1px solid var(--line);
        background: rgba(251, 250, 245, 0.82);
        font: 11px/1.4 Consolas, monospace;
    }
    .fm-sync-row:first-child { border-top: 1px solid var(--line); }
    .fm-sync-event { color: var(--forest-soft); font-weight: 700; }
    .fm-conflict {
        margin: 0.55rem 0;
        padding: 0.85rem 0.95rem;
        border: 1px solid var(--line);
        border-left: 3px solid var(--signal);
        border-radius: 3px;
        background: var(--white);
    }
    .fm-conflict-head {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        gap: 0.5rem;
        color: var(--forest);
        font: 700 11px/1.4 Consolas, monospace;
    }
    .fm-conflict-versions {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.7rem;
        margin-top: 0.65rem;
    }
    .fm-version {
        padding: 0.65rem;
        border-top: 1px solid var(--line);
        color: var(--muted);
        font: 11px/1.45 Consolas, monospace;
        overflow-wrap: anywhere;
    }
    .fm-version strong { display: block; margin-bottom: 0.3rem; color: var(--ink); }
    .fm-empty {
        padding: 1rem 0.55rem;
        border-top: 1px solid var(--line);
        color: var(--muted);
        font: italic 14px Georgia, serif;
    }
    .fm-stat-label {
        color: var(--muted);
        font: 700 9px/1.2 Consolas, monospace;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    @media (max-width: 700px) {
        .fm-header { align-items: flex-start; flex-direction: column; min-height: 0; padding: 1rem; }
        .fm-title { font-size: 34px; }
        .fm-header-note { min-width: 0; padding: 0.25rem 0 0.25rem 0.7rem; text-align: left; }
        [data-testid="stTabs"] [data-baseweb="tab-list"] { overflow-x: auto; }
        [data-testid="stTabs"] button[role="tab"] { flex: 0 0 auto; padding: 0 0.55rem; font-size: 9px; }
        .fm-record { grid-template-columns: 32px minmax(0, 1fr); gap: 0.45rem; }
        .fm-record-meta { grid-column: 2; justify-content: flex-start; text-align: left; }
        .fm-record-reason { grid-column: 2; margin-top: 0; }
        .fm-sync-row { grid-template-columns: 1fr 1fr; gap: 0.35rem 0.7rem; }
        .fm-sync-row span:first-child { grid-column: 1 / -1; }
        .fm-conflict-versions { grid-template-columns: 1fr; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _render_record_rows(records: list[dict], mode: str = "memory") -> None:
    if not records:
        st.markdown('<div class="fm-empty">Nothing recorded here yet.</div>', unsafe_allow_html=True)
        return

    rendered = []
    for index, record in enumerate(records, start=1):
        payload = record.get("payload", record)
        text = html.escape(str(payload.get("text", payload.get("Field note", ""))))
        device = html.escape(str(payload.get("device_id", "")))
        sensitivity = html.escape(str(payload.get("sensitivity", "")))
        status = str(payload.get("sync_status", ""))
        decision = str(payload.get("sync_decision", ""))
        reason = html.escape(str(payload.get("sync_reason", "")))
        score = record.get("score")
        if mode == "match" and score is not None:
            metadata = (
                f'<span class="fm-score">{float(score):.3f}</span>'
                f'<span class="fm-tag">{device or "LOCAL"}</span>'
            )
        else:
            status_class = "fm-tag-signal" if status == "local_only" else "fm-tag"
            metadata = (
                f'<span class="fm-tag {status_class}">{html.escape(status or "local")}</span>'
                f'<span class="fm-tag">{html.escape(decision or "pending")}</span>'
                f'<span class="fm-tag">{sensitivity}</span>'
            )
        reason_row = f'<div class="fm-record-reason">{reason}</div>' if reason else ""
        rendered.append(
            '<div class="fm-record">'
            f'<div class="fm-record-index">{index:02d}</div>'
            f'<div class="fm-record-text">{text}</div>'
            f'<div class="fm-record-meta">{metadata}</div>'
            f"{reason_row}</div>"
        )
    st.markdown(
        '<div class="fm-record-list">' + "".join(rendered) + "</div>",
        unsafe_allow_html=True,
    )


st.sidebar.markdown('<div class="fm-rail-mark">FM</div>', unsafe_allow_html=True)
st.sidebar.markdown("### FIELD DESK")
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
    help="When enabled, the sync worker skips every network call.",
)
_apply_offline_setting()
policy_name = os.getenv("SYNC_POLICY", "model").strip().lower()
st.sidebar.caption(f"Active sync policy · {policy_name}")

if not device_id:
    st.error("Enter a device ID to continue.")
    st.stop()

previous_worker_device = st.session_state.get("sync_worker_device")
if previous_worker_device and previous_worker_device != device_id:
    stop_sync_worker(previous_worker_device)
start_sync_worker(device_id)
st.session_state["sync_worker_device"] = device_id

st.markdown(
    """
    <div class="fm-header">
      <div>
        <p class="fm-eyebrow">Code Cubicle 6.0 / Field operations</p>
        <h1 class="fm-title">Field Memory</h1>
      </div>
      <div class="fm-header-note">LOCAL FIRST<br>SEARCH · DECIDE · SYNC</div>
    </div>
    """,
    unsafe_allow_html=True,
)
offline_label = "OFFLINE · sync paused" if st.session_state["offline_mode"] else "ONLINE · sync active"
offline_class = "fm-status-offline" if st.session_state["offline_mode"] else "fm-status-live"
st.markdown(
    f'<div class="fm-status-strip"><span><strong>DEVICE</strong> {device_id}</span>'
    f'<span class="{offline_class}"><strong>{offline_label}</strong></span>'
    f'<span><strong>POLICY</strong> {policy_name}</span></div>',
    unsafe_allow_html=True,
)

desk_tab, sync_tab, conflicts_tab, policy_tab = st.tabs(
    ("Field desk", "Sync log", "Conflicts", "Policy & metrics")
)

with desk_tab:
    st.markdown(
        '<p class="fm-tab-note">Capture observations and retrieve them from this device or its synced shard.</p>',
        unsafe_allow_html=True,
    )
    add_column, search_column = st.columns([0.9, 1.1], gap="large")

    with add_column:
        st.subheader("New field note")
        with st.form("add_memory_form", clear_on_submit=True):
            memory_text = st.text_area(
                "Observation",
                placeholder="Record an inspection, reading, or field change",
                height=135,
            )
            sensitivity = st.selectbox(
                "Sensitivity",
                options=("low", "medium", "high"),
                index=0,
            )
            add_submitted = st.form_submit_button("Save note", icon=":material/add:")

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
        st.subheader("Search field notes")
        with st.form("search_form"):
            query_text = st.text_input(
                "Search query",
                placeholder="Pressure readings near the north gate",
            )
            top_k = st.number_input("Maximum results", min_value=1, max_value=20, value=5)
            search_submitted = st.form_submit_button(
                "Search offline",
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
            st.markdown(
                '<div class="fm-section-label">Retrieval result / measured local latency</div>',
                unsafe_allow_html=True,
            )
            st.metric("Search latency", f"{st.session_state['search_latency_ms']:.2f} ms")
            results = st.session_state["search_results"]
            _render_record_rows(results, mode="match")

    st.divider()
    st.subheader("Ask from your notes")
    with st.form("ask_form"):
        question = st.text_input("Question", placeholder="What did the team record about the pump?")
        ask_submitted = st.form_submit_button("Ask locally", icon=":material/chat:")

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
        st.markdown(
            '<div class="fm-section-label">FIELD RESPONSE / GROUNDED IN LOCAL RECORDS</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="fm-record-text" style="font-size:19px;padding:0.4rem 0 0.8rem">'
            + html.escape(st.session_state["ask_answer"])
            + "</div>",
            unsafe_allow_html=True,
        )
        sources = st.session_state["ask_sources"]
        if sources:
            st.markdown(
                '<div class="fm-section-label">SOURCE NOTES</div>',
                unsafe_allow_html=True,
            )
            _render_record_rows(sources, mode="match")

    st.divider()
    st.subheader("Stored field notes")
    try:
        memories = list_memories(device_id, limit=12)
        if memories:
            _render_record_rows(memories)
        else:
            st.info("No field notes on this device yet.")
    except Exception as error:
        st.error(f"Could not load memories: {error}")

with sync_tab:
    st.markdown(
        '<p class="fm-tab-note">Device-local shard inventory and the latest server synchronization events.</p>',
        unsafe_allow_html=True,
    )
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
        for counts in counts_by_device:
            st.markdown(
                f'<div class="fm-section-label">{html.escape(counts["Device"])} / SHARD INVENTORY</div>'
                '<div class="fm-status-strip">'
                f'<span><strong>MUTABLE</strong> {counts["Mutable"]}</span>'
                f'<span><strong>IMMUTABLE</strong> {counts["Immutable"]}</span>'
                f'<span><strong>TOTAL</strong> {counts["Total"]}</span>'
                "</div>",
                unsafe_allow_html=True,
            )

    sync_entries = read_sync_log(limit=12)
    if sync_entries:
        sync_rows = []
        for entry in sync_entries:
            timestamp = time.strftime(
                "%H:%M:%S",
                time.localtime(entry.get("timestamp", 0)),
            )
            device = html.escape(str(entry.get("device_id", "")))
            event = html.escape(str(entry.get("event", ""))).replace("_", " ").upper()
            sync_rows.append(
                '<div class="fm-sync-row">'
                f'<span>{timestamp} · {device}</span>'
                f'<span class="fm-sync-event">{event}</span>'
                f'<span>UP {entry.get("uploaded", 0)}</span>'
                f'<span>SNAP {entry.get("snapshot_bytes", 0)}</span>'
                f'<span>PURGE {entry.get("purged", 0)}</span>'
                f'<span>CONFLICT {len(entry.get("conflicts", []))}</span>'
                "</div>"
            )
        st.markdown("".join(sync_rows), unsafe_allow_html=True)
    else:
        st.info("No sync activity recorded yet.")

with conflicts_tab:
    st.markdown(
        '<p class="fm-tab-note">Inspect edits that shared an ID and the timestamp rule used to resolve them.</p>',
        unsafe_allow_html=True,
    )
    conflicts = read_conflicts()[-8:]
    if conflicts:
        conflict_rows = []
        for conflict in reversed(conflicts):
            local = conflict["local_version"]
            server = conflict["server_version"]
            conflict_rows.append(
                '<article class="fm-conflict">'
                '<div class="fm-conflict-head">'
                f'<span>ID {html.escape(conflict["point_id"])}</span>'
                f'<span>WINNER {html.escape(conflict["winner"])}</span>'
                f'<span>{html.escape(conflict["reason"])}</span>'
                "</div>"
                '<div class="fm-conflict-versions">'
                '<div class="fm-version">'
                f'<strong>LOCAL · {html.escape(local["device_id"])} · {local["timestamp"]:.3f}</strong>'
                f'{html.escape(local["text"])}</div>'
                '<div class="fm-version">'
                f'<strong>SERVER · {html.escape(server["device_id"])} · {server["timestamp"]:.3f}</strong>'
                f'{html.escape(server["text"])}</div>'
                "</div></article>"
            )
        st.markdown("".join(conflict_rows), unsafe_allow_html=True)
    else:
        st.info("No conflicts recorded.")

with policy_tab:
    st.markdown(
        f'<p class="fm-tab-note">Active sync policy: <strong>{policy_name}</strong>. '
        "Every write records its decision and a one-line explanation.</p>",
        unsafe_allow_html=True,
    )
    metrics_path = Path(__file__).resolve().parents[1] / "data" / "policy_metrics.json"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            metric_rows = []
            for label, key in (
                ("ACCURACY", "accuracy"),
                ("SYNC PRECISION", "sync_precision"),
                ("SYNC RECALL", "sync_recall"),
            ):
                metric_rows.append(
                    '<div class="fm-status-strip">'
                    f'<span><strong>{label}</strong></span>'
                    f'<span style="font:700 24px Georgia,serif;color:var(--forest)">{metrics[key]:.1%}</span>'
                    "</div>"
                )
            metric_columns = st.columns(3)
            for column, metric_row in zip(metric_columns, metric_rows):
                with column:
                    st.markdown(metric_row, unsafe_allow_html=True)
            st.caption(
                f"{metrics['model']} · {metrics['held_out_samples']} held-out synthetic examples; "
                "labels came from the Phase 4 rules."
            )
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            st.error(f"Could not load policy metrics: {error}")

    try:
        policy_memories = list_memories(device_id, limit=12)
        policy_rows = [
            {
                "Field note": item["payload"].get("text", ""),
                "Decision": item["payload"].get("sync_decision", ""),
                "Confidence": item["payload"].get("sync_confidence", ""),
                "Novelty": item["payload"].get("novelty_score", ""),
                "Reason": item["payload"].get("sync_reason", ""),
            }
            for item in policy_memories
            if item["payload"].get("sync_decision")
        ]
        if policy_rows:
            _render_record_rows(
                [
                    {
                        "payload": {
                            "text": row["Field note"],
                            "sync_decision": row["Decision"],
                            "sync_confidence": row["Confidence"],
                            "sync_status": f"conf {row['Confidence']} / novelty {row['Novelty']}",
                            "sync_reason": row["Reason"],
                        }
                    }
                    for row in policy_rows
                ]
            )
        else:
            st.info("No policy-scored writes on this device yet.")
    except Exception as error:
        st.error(f"Could not load policy decisions: {error}")