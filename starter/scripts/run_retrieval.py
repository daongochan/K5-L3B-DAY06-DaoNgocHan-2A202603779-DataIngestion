"""Run all three strategies and save full top-3 traces.

Strategies:
  A_fixed  fixed 500 / overlap 150, no filter
  B_para   paragraph-aligned 700 with breadcrumb, no filter
  C_para_filter  same chunks and same embedding as B, plus the metadata filter
                 supplied by the question (only 4 questions carry one)

B and C share chunk IDs and vectors, so the only difference between them is
filtering. That makes the B–C comparison a clean measurement of metadata filter
effect, as the lab requires.

Run from starter/:  python scripts/run_retrieval.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
sys.path.insert(0, str(STARTER))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(STARTER / ".env")

from src.embeddings import DEFAULT_MODEL, SentenceTransformerEmbedder  # noqa: E402
from src.evaluation import evaluate_query, summarize  # noqa: E402
from src.store import PgVectorStore  # noqa: E402

RESULTS = STARTER / "results"
BENCHMARK = ROOT / "benchmark" / "questions.json"

TOP_K = 3

# strategy name -> (stored strategy, apply question filter)
STRATEGIES = {
    "A_fixed": ("A_fixed", False),
    "B_para": ("B_para", False),
    "C_para_filter": ("B_para", True),
}


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("FAIL: DATABASE_URL is not set")
        return 1

    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    embedder = SentenceTransformerEmbedder(os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL)
    store = PgVectorStore(database_url, embedder.dimensions)

    query_vectors = {}
    traces = []
    latencies: dict[str, list[float]] = {name: [] for name in STRATEGIES}

    for name, (stored, use_filter) in STRATEGIES.items():
        for question in benchmark["questions"]:
            if question["id"] not in query_vectors:
                query_vectors[question["id"]] = embedder.embed_query(question["question"])
            filters = question["filter"] if use_filter and question.get("filter") else None

            started = time.perf_counter()
            hits = store.search(
                stored, query_vectors[question["id"]], top_k=TOP_K, filters=filters
            )
            latencies[name].append((time.perf_counter() - started) * 1000)

            traces.append(evaluate_query(question, hits, name, filters))

    summary = summarize(traces)

    out = RESULTS / "retrieval_traces.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace, ensure_ascii=False) + "\n")

    metrics = {
        "top_k": TOP_K,
        "embedding_model": embedder.model_name,
        "dimensions": embedder.dimensions,
        "strategies": {
            "A_fixed": {"stored_strategy": "A_fixed", "filter": "none"},
            "B_para": {"stored_strategy": "B_para", "filter": "none"},
            "C_para_filter": {
                "stored_strategy": "B_para",
                "filter": "question-supplied metadata filter (page_type, article)",
                "unchanged_vs_B": ["chunking", "embedding", "store", "metric", "top_k"],
            },
        },
        "latency_ms": {
            name: {
                "mean": round(statistics.mean(values), 2),
                "median": round(statistics.median(values), 2),
                "max": round(max(values), 2),
                "n": len(values),
            }
            for name, values in latencies.items()
        },
        "summary": summary,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/run_retrieval.py",
    }
    (RESULTS / "retrieval_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for name in STRATEGIES:
        for split in ("dev", "test", "all"):
            item = summary[name].get(split)
            if not item:
                continue
            print(
                f"{name:15s} {split:5s} Hit@1 {item['hit_at_1']}/{item['n']}  "
                f"Hit@3 {item['hit_at_3']}/{item['n']}  "
                f"filter {item['filter_compliant']}/{item['filter_questions']}"
            )

    print()
    filter_problems = [
        f"{name}: filter compliance {item['filter_compliant']}/{item['filter_questions']}"
        for name, splits in summary.items()
        for split, item in splits.items()
        if split == "all" and item["filter_questions"] and item["filter_compliant"] < item["filter_questions"]
    ]
    for problem in filter_problems:
        print(f"FAIL: {problem}")
    return 1 if filter_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
