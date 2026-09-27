import time


RECENT_SECONDS = 7 * 24 * 60 * 60
NOVELTY_SIMILARITY_THRESHOLD = 0.75
SYNC_SCORE_THRESHOLD = 0.50


def decide(payload: dict, novelty_score: float) -> tuple[str, float, str]:
    age_seconds = max(0.0, time.time() - float(payload.get("timestamp", time.time())))
    access_count = max(0, int(payload.get("access_count", 0)))
    size_bytes = max(0, int(payload.get("size_bytes", 0)))
    sensitivity = str(payload.get("sensitivity", "low")).lower()
    similarity = max(-1.0, min(1.0, float(novelty_score)))

    score = 0.0
    reasons = []
    if age_seconds <= RECENT_SECONDS:
        score += 0.25
        reasons.append("recent")
    else:
        reasons.append("stale")

    if access_count >= 3:
        score += 0.25
        reasons.append("frequently accessed")

    if similarity <= NOVELTY_SIMILARITY_THRESHOLD:
        score += 0.45
        reasons.append("novel")
    else:
        reasons.append("similar to server-known memories")

    if size_bytes > 8192:
        score -= 0.30
        reasons.append("large")

    if sensitivity == "medium":
        score -= 0.15
        reasons.append("medium sensitivity")
    elif sensitivity == "high":
        score -= 0.70
        reasons.append("high sensitivity")

    decision = "sync" if score >= SYNC_SCORE_THRESHOLD else "keep_local"
    confidence = min(0.99, 0.5 + abs(score - SYNC_SCORE_THRESHOLD))
    reason = (
        f"{decision}: {', '.join(reasons)} "
        f"(score={score:.2f}, threshold={SYNC_SCORE_THRESHOLD:.2f})"
    )
    return decision, round(confidence, 2), reason