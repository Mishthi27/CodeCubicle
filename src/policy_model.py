import csv
import json
import time
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

from src.policy_rules import NOVELTY_SIMILARITY_THRESHOLD, RECENT_SECONDS
from src.shard import DATA_ROOT


TRAINING_DATA_PATH = DATA_ROOT / "policy_training.csv"
MODEL_PATH = DATA_ROOT / "policy_model.joblib"
METRICS_PATH = DATA_ROOT / "policy_metrics.json"
FEATURE_NAMES = (
    "recent",
    "frequently_accessed",
    "novel",
    "large",
    "medium_sensitivity",
    "high_sensitivity",
)

_model = None


def _feature_values(
    age_seconds: float,
    access_count: int,
    novelty_score: float,
    size_bytes: int,
    sensitivity: str,
) -> list[int]:
    similarity = max(-1.0, min(1.0, float(novelty_score)))
    sensitivity = str(sensitivity).lower()
    return [
        int(float(age_seconds) <= RECENT_SECONDS),
        int(int(access_count) >= 3),
        int(similarity <= NOVELTY_SIMILARITY_THRESHOLD),
        int(int(size_bytes) > 8192),
        int(sensitivity == "medium"),
        int(sensitivity == "high"),
    ]


def _features(payload: dict, novelty_score: float, now: float) -> list[int]:
    age_seconds = max(
        0.0,
        float(now) - float(payload.get("timestamp", now)),
    )
    return _feature_values(
        age_seconds,
        int(payload.get("access_count", 0)),
        novelty_score,
        int(payload.get("size_bytes", 0)),
        str(payload.get("sensitivity", "low")),
    )


def _load_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"trained policy not found at {MODEL_PATH}; "
                "run scripts/simulate_usage_logs.py before using SYNC_POLICY=model"
            )
        _model = joblib.load(MODEL_PATH)
    return _model


def decide(payload: dict, novelty_score: float) -> tuple[str, float, str]:
    classifier = _load_model()
    features = _features(payload, novelty_score, time.time())
    prediction = str(classifier.predict([features])[0])
    probabilities = classifier.predict_proba([features])[0]
    confidence = float(max(probabilities))

    recent, frequently_accessed, novel, large, medium_sensitive, high_sensitive = features
    similarity_description = "novel" if novel else "similar"
    sensitivity = "high" if high_sensitive else "medium" if medium_sensitive else "low"
    reason = (
        f"trained logistic regression: {prediction}; "
        f"recent={bool(recent)}, frequently_accessed={bool(frequently_accessed)}, "
        f"server_similarity={similarity_description}, large={bool(large)}, "
        f"sensitivity={sensitivity}"
    )
    return prediction, round(confidence, 4), reason


def train_model(
    training_data_path: Path = TRAINING_DATA_PATH,
    model_path: Path = MODEL_PATH,
    metrics_path: Path = METRICS_PATH,
) -> dict:
    rows = []
    with training_data_path.open("r", newline="", encoding="utf-8") as training_file:
        for row in csv.DictReader(training_file):
            rows.append(
                (
                    _feature_values(
                        float(row["age_seconds"]),
                        int(row["access_count"]),
                        float(row["novelty_score"]),
                        int(row["size_bytes"]),
                        row["sensitivity"],
                    ),
                    row["decision"],
                )
            )

    features = [row[0] for row in rows]
    labels = [row[1] for row in rows]
    train_features, test_features, train_labels, test_labels = train_test_split(
        features,
        labels,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    classifier = LogisticRegression(max_iter=2000, random_state=42)
    classifier.fit(train_features, train_labels)
    predictions = classifier.predict(test_features)

    metrics = {
        "model": "LogisticRegression",
        "label_source": "Phase 4 rule-based policy",
        "feature_names": list(FEATURE_NAMES),
        "training_samples": len(train_labels),
        "held_out_samples": len(test_labels),
        "accuracy": round(float(accuracy_score(test_labels, predictions)), 6),
        "sync_precision": round(
            float(precision_score(test_labels, predictions, pos_label="sync", zero_division=0)),
            6,
        ),
        "sync_recall": round(
            float(recall_score(test_labels, predictions, pos_label="sync", zero_division=0)),
            6,
        ),
        "sync_f1": round(
            float(f1_score(test_labels, predictions, pos_label="sync", zero_division=0)),
            6,
        ),
        "random_state": 42,
        "test_fraction": 0.2,
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(classifier, model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    global _model
    _model = classifier
    return metrics


if __name__ == "__main__":
    print(json.dumps(train_model(), indent=2))