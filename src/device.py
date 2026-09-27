import argparse
import json
import logging
import os
import sys

from src.read_path import search
from src.shard import close_all_shards
from src.write_path import insert_memory


def _read_stdin(prompt: str) -> str:
    if sys.stdin.isatty():
        return input(prompt).strip()
    return sys.stdin.read().strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline field memory assistant")
    parser.add_argument(
        "--device-id",
        default=os.getenv("DEVICE_ID", "device-a"),
    )
    actions = parser.add_subparsers(dest="action", required=True)
    add_parser = actions.add_parser("add", help="insert a memory from stdin")
    add_parser.add_argument(
        "--sensitivity",
        choices=("low", "medium", "high"),
        default="low",
    )
    search_parser = actions.add_parser("search", help="search memories from stdin")
    search_parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.action == "add":
            text = _read_stdin("Memory: ")
            point_id = insert_memory(text, args.device_id, args.sensitivity)
            print(f"Inserted memory id={point_id}")
        else:
            query = _read_stdin("Search: ")
            results = search(query, args.top_k, args.device_id)
            print(json.dumps(results, indent=2, ensure_ascii=False))
    finally:
        close_all_shards()


if __name__ == "__main__":
    main()