def answer(query: str, retrieved_memories: list[dict]) -> str:
    """Build a grounded local response when a llama.cpp runtime/model is unavailable."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if not retrieved_memories:
        return "I could not find a matching memory on this device."

    excerpts = []
    seen_texts = set()
    for result in retrieved_memories[:3]:
        payload = result.get("payload", result)
        text = str(payload.get("text", "")).strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            excerpts.append(text)

    if not excerpts:
        return "I found matching records, but none contained readable memory text."
    if len(excerpts) == 1:
        return f"The closest local memory says: {excerpts[0]}"
    return "Relevant local memories say: " + "; ".join(excerpts)