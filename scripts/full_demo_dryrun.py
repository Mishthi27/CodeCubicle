import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    ("Phase 1 offline memory search", "scripts/smoke_test_phase1.py"),
    ("Phase 2 shard merge and dedupe", "scripts/smoke_test_phase2.py"),
    ("Phase 3 online sync", "scripts/smoke_test_phase3.py"),
    ("Phase 3 offline skip", "scripts/smoke_test_phase3.py", "--offline-branch"),
    ("Phase 4 policy and conflicts", "scripts/smoke_test_phase4.py"),
    ("Phase 5 trained policy integration", "scripts/smoke_test_phase5.py"),
    ("Phase 6 two-device rehearsal", "scripts/smoke_test_phase6.py"),
)


def main() -> None:
    os.environ["OFFLINE"] = "0"
    os.environ["SYNC_POLICY"] = "model"
    started = time.perf_counter()
    print("FULL_DEMO_DRYRUN_STARTED", flush=True)

    for step in STEPS:
        label, script, *arguments = step
        command = [sys.executable, script, *arguments]
        print(f"\n===== {label} =====", flush=True)
        step_started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, check=False)
        elapsed = time.perf_counter() - step_started
        if result.returncode != 0:
            print(
                f"FULL_DEMO_DRYRUN_FAILED step={label!r} "
                f"exit_code={result.returncode} elapsed_s={elapsed:.2f}",
                flush=True,
            )
            raise SystemExit(result.returncode)
        print(f"STEP_PASS elapsed_s={elapsed:.2f}", flush=True)

    print(
        f"FULL_DEMO_DRYRUN_PASS phases={len(STEPS)} "
        f"elapsed_s={time.perf_counter() - started:.2f}",
        flush=True,
    )


if __name__ == "__main__":
    main()