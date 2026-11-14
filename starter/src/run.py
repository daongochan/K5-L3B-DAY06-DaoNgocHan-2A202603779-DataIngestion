"""End-to-end pipeline: corpus -> chunks -> vectors -> retrieval -> metrics.

Running this command reproduces every number in the report:

    python -m src.run

It is deliberately thin: each step lives in its own module and its own script so
a failure names the stage that broke. Nothing falls back to mock vectors — if the
embedding model or the database is unavailable, the run fails loudly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
RESULTS = STARTER / "results"

STEPS = (
    ("audit_pages.py", "kiểm tra trang, sinh page_audit.*"),
    ("extract_structure.py", "trích Chương/Mục/Điều"),
    ("verify_manifest.py", "đối chiếu manifest với artifact"),
    ("verify_benchmark.py", "kiểm chứng evidence benchmark"),
    ("export_chunks.py", "xuất hai cấu hình chunk"),
    ("check_chunk_coverage.py", "kiểm tra evidence nằm trọn trong chunk"),
    ("pick_coherence_samples.py", "chốt 10 vị trí chấm coherence"),
    ("ingest_vectors.py", "nhúng vector và nạp vào pgvector"),
    ("run_retrieval.py", "chạy ba chiến lược, lưu trace top-3"),
    ("audit_retrieval.py", "audit metadata và chấm grounding"),
)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(STARTER / ".env")

    if not os.environ.get("DATABASE_URL"):
        print("FAIL: DATABASE_URL chưa đặt. Copy starter/.env.example thành starter/.env")
        raise SystemExit(1)

    failures = []
    env = dict(os.environ)
    for script, description in STEPS:
        path = STARTER / "scripts" / script
        print(f"\n=== {script} — {description} ===")
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=STARTER,
            text=True,
            capture_output=True,
            env=env,
        )
        output = (result.stdout or "") + (result.stderr or "")
        for line in output.splitlines():
            if line.startswith(("FAIL", "WARN")) or " OK" in line or line.startswith("  "):
                print(line)
        if result.returncode != 0:
            failures.append(script)

    print()
    if failures:
        print(f"FAIL: {len(failures)} bước lỗi: {failures}")
        raise SystemExit(1)

    metrics = json.loads((RESULTS / "retrieval_metrics.json").read_text(encoding="utf-8"))
    print("Kết quả (top-3):")
    for strategy, splits in metrics["summary"].items():
        line = "  ".join(
            f"{split} Hit@1 {item['hit_at_1']}/{item['n']} Hit@3 {item['hit_at_3']}/{item['n']}"
            for split, item in splits.items()
            if split in ("dev", "test")
        )
        print(f"  {strategy:15s} {line}")
    print(f"\nTrace: {RESULTS / 'retrieval_traces.jsonl'}")


if __name__ == "__main__":
    main()
