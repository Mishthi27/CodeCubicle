import argparse
import csv
import random
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.policy_rules import decide
from src.policy_model import TRAINING_DATA_PATH


FIELDS = (
    "age_seconds",
    "access_count",
    "novelty_score",
    "size_bytes",
    "sensitivity",
    "decision",
    "reason",
)


def generate_usage_logs(
    output_path: Path = TRAINING_DATA_PATH,
    sample_count: int = 4000,
    seed: int = 42,
) -> tuple[list[dict], Counter]:
    randomizer = random.Random(seed)
    generated_at = time.time()
    rows = []
    labels = Counter()
    for _ in range(sample_count):
        age_seconds = (
            randomizer.uniform(0, 7 * 24 * 60 * 60)
            if randomizer.random() < 0.5
            else randomizer.uniform(7 * 24 * 60 * 60 + 1, 365 * 24 * 60 * 60)
        )
        access_count = randomizer.randint(0, 2) if randomizer.random() < 0.5 else randomizer.randint(3, 20)
        novelty_score = (
            randomizer.uniform(-0.1, 0.75)
            if randomizer.random() < 0.5
            else randomizer.uniform(0.751, 1.0)
        )
        size_bytes = randomizer.randint(32, 8192) if randomizer.random() < 0.75 else randomizer.randint(8193, 25000)
        sensitivity = randomizer.choices(
            ("low", "medium", "high"),
            weights=(0.65, 0.2, 0.15),
            k=1,
        )[0]
        payload = {
            "timestamp": generated_at - age_seconds,
            "access_count": access_count,
            "size_bytes": size_bytes,
            "sensitivity": sensitivity,
        }
        decision, _, reason = decide(payload, novelty_score, now=generated_at)
        rows.append(
            {
                "age_seconds": round(age_seconds, 2),
                "access_count": access_count,
                "novelty_score": round(novelty_score, 5),
                "size_bytes": size_bytes,
                "sensitivity": sensitivity,
                "decision": decision,
                "reason": reason,
            }
        )
        labels[decision] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as training_file:
        writer = csv.DictWriter(training_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows, labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rule-labeled memory usage data")
    parser.add_argument("--count", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=TRAINING_DATA_PATH)
    args = parser.parse_args()
    rows, labels = generate_usage_logs(args.output, args.count, args.seed)
    print(f"DATASET={args.output} rows={len(rows)} seed={args.seed}")
    print(f"LABEL_COUNTS={dict(labels)}")
    print("SAMPLE_ROWS=")
    for row in rows[:5]:
        print(row)


if __name__ == "__main__":
    main()