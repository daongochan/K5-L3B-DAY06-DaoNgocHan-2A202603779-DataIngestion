"""Check that each chunking strategy can actually surface the benchmark evidence.

Retrieval quality cannot be measured before embeddings exist, but a cheaper and
more fundamental question can be answered now: does any chunk contain the full
evidence string for each question? If no chunk contains it, the strategy has
destroyed the evidence before retrieval even starts, and no embedding model can
recover it.

This is a *ceiling* check, not a retrieval score. It is reported per split so a
strategy that only breaks test evidence is visible.

Run from starter/:  python scripts/check_chunk_coverage.py
"""
from __future__ import annotations

import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
RESULTS = STARTER / "results"
BENCHMARK = ROOT / "benchmark" / "questions.json"

STRATEGIES = {
    "A_fixed": RESULTS / "chunks_A_fixed.jsonl",
    "B_para": RESULTS / "chunks_B_para.jsonl",
}


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def load_chunks(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    questions = benchmark["questions"]

    report: dict = {
        "note": (
            "Coverage = có ít nhất một chunk chứa trọn chuỗi evidence. Đây là trần "
            "lý thuyết, không phải Hit@k: một chunk có thể chứa evidence nhưng vẫn "
            "không được xếp hạng trong top-3."
        ),
        "strategies": {},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/check_chunk_coverage.py",
    }

    failures: list[str] = []

    for name, path in STRATEGIES.items():
        chunks = load_chunks(path)
        folded = [(chunk, fold(chunk["text"])) for chunk in chunks]

        per_split = {"dev": [0, 0], "test": [0, 0]}
        missing: list[dict] = []
        extra_chunks: list[int] = []

        for question in questions:
            split = question["split"]
            per_split[split][1] += 1
            covered = False
            for gold in question["gold"]:
                evidence = fold(gold["evidence"])
                page = gold["physical_page"]
                page_chunks = [
                    (chunk, text)
                    for chunk, text in folded
                    if chunk["page"] == page and evidence in text
                ]
                if page_chunks:
                    covered = True
                    extra_chunks.append(len(page_chunks))
                    break
            if covered:
                per_split[split][0] += 1
            else:
                missing.append({"id": question["id"], "split": split})

        report["strategies"][name] = {
            "chunks": len(chunks),
            "dev_covered": per_split["dev"][0],
            "dev_total": per_split["dev"][1],
            "test_covered": per_split["test"][0],
            "test_total": per_split["test"][1],
            "missing": missing,
            "avg_chunks_per_gold_evidence": round(
                sum(extra_chunks) / len(extra_chunks), 2
            )
            if extra_chunks
            else 0.0,
        }

        if missing:
            failures.append(f"{name}: evidence not contained in any chunk for {missing}")

    (RESULTS / "chunk_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for name, item in report["strategies"].items():
        print(
            f"{name}: dev {item['dev_covered']}/{item['dev_total']} "
            f"test {item['test_covered']}/{item['test_total']} "
            f"avg chunks per evidence {item['avg_chunks_per_gold_evidence']}"
        )

    for failure in failures:
        print(f"FAIL: {failure}")

    if failures:
        return 1

    print("coverage OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
