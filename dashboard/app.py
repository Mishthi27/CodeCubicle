import os
import time

import streamlit as st

from src.read_path import list_memories, search
from src.write_path import insert_memory


st.set_page_config(page_title="Field Memory", layout="wide")
st.title("Field Memory")
st.caption("Local memories · offline search")

device_id = st.sidebar.text_input(
    "Device ID",
    value=os.getenv("DEVICE_ID", "device-a"),
).strip()

if not device_id:
    st.error("Enter a device ID to continue.")
    st.stop()

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
                    }
                    for result in results
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No matching memories.")

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
                    "Updated": time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(item["payload"].get("timestamp", 0)),
                    ),
                }
                for item in memories
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No memories stored on this device yet.")
except Exception as error:
    st.error(f"Could not load memories: {error}")