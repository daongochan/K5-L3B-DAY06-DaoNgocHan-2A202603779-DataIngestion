"""Ingest both chunk configurations into pgvector with a real embedding model.

Proves the three things the checkpoint asks for:
  * both strategies are stored and searchable,
  * re-ingestion does not duplicate rows (run twice, count must be identical),
  * the embedding model, dimensions, metric and timing are recorded.

Run from starter/:  python scripts/ingest_vectors.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(STARTER / ".env")

from src.chunking import apply_structure, by_paragraph, fixed_size  # noqa: E402
from src.embeddings import DEFAULT_MODEL, SentenceTransformerEmbedder  # noqa: E402
from src.ingestion import load_pdf  # noqa: E402
from src.store import PgVectorStore  # noqa: E402


def package_version(name: str) -> str:
    """Read an installed version without assuming the package exposes __version__."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return "unknown"

PDF = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"
DOCUMENT_ID = "nghi-dinh-13-2023-nd-cp"
SOURCE = "data/nghi_dinh_13_2023_nd_cp.pdf"
RESULTS = STARTER / "results"

FIXED_SIZE = 500
FIXED_OVERLAP = 150
PARA_MAX = 700


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("FAIL: DATABASE_URL is not set; copy .env.example to .env")
        return 1

    model_name = os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL
    started = time.time()

    print(f"embedding model: {model_name}")
    embedder = SentenceTransformerEmbedder(model_name)
    print(f"dimensions: {embedder.dimensions}")

    pages = apply_structure(load_pdf(PDF, DOCUMENT_ID, SOURCE))
    content = [page for page in pages if page.metadata["page_type"] != "phu_luc_muc_luc"]
    configs = {
        "A_fixed": [chunk for page in content for chunk in fixed_size(page, FIXED_SIZE, FIXED_OVERLAP)],
        "B_para": [chunk for page in content for chunk in by_paragraph(page, PARA_MAX)],
    }

    store = PgVectorStore(database_url, embedder.dimensions)
    store.create_schema()

    timings: dict[str, dict] = {}
    # Two passes: the second one proves re-ingestion is idempotent.
    for pass_number in (1, 2):
        for strategy, chunks in configs.items():
            pass_started = time.time()
            vectors = embedder.embed_documents([chunk.text for chunk in chunks])
            embed_seconds = time.time() - pass_started
            write_started = time.time()
            counts = store.upsert(strategy, chunks, vectors)
            write_seconds = time.time() - write_started
            total = store.count(strategy)

            if pass_number == 2:
                timings[strategy] = {
                    "chunks": len(chunks),
                    "embed_seconds": round(embed_seconds, 2),
                    "write_seconds": round(write_seconds, 2),
                    "rows_in_store_after_second_pass": total,
                    "duplicate_rows": total - len(chunks),
                    "written": counts["written"],
                    "deleted_stale": counts["deleted"],
                }
                status = "OK" if total == len(chunks) else "FAIL"
                print(
                    f"{strategy}: pass2 embed {embed_seconds:.1f}s write {write_seconds:.1f}s "
                    f"rows={total} expected={len(chunks)} {status}"
                )

    report = {
        "embedding": {
            "provider": "sentence-transformers (local, CPU)",
            "model_name": model_name,
            "dimensions": embedder.dimensions,
            "document_prefix": "passage: ",
            "query_prefix": "query: ",
            "normalized": True,
            "library_versions": {
                "sentence-transformers": package_version("sentence-transformers"),
                "torch": package_version("torch"),
                "numpy": package_version("numpy"),
                "psycopg": package_version("psycopg"),
                "pgvector": package_version("pgvector"),
            },
        },
        "vector_store": {
            "engine": "PostgreSQL + pgvector (Docker Compose, project day6_student_starter)",
            "table": "chunks",
            "metric": "cosine",
            "operator": "<=>",
            "index_type": "exact scan (sequential) — corpus has ~200 chunks, ANN would add approximation error for no real gain",
            "dimensions": embedder.dimensions,
            "filter_columns": ["document_id", "page", "printed_page", "page_type", "article", "chapter", "section"],
        },
        "cost": {
            "api_cost_usd": 0.0,
            "note": "Model chạy local trên CPU, không gọi API trả phí.",
        },
        "timings_second_pass": timings,
        "total_seconds": round(time.time() - started, 1),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/ingest_vectors.py",
    }
    (RESULTS / "ingest_vectors.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    problems = [
        f"{strategy}: duplicate rows after re-ingest"
        for strategy, item in timings.items()
        if item["duplicate_rows"] != 0
    ]
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1

    print(f"ingest OK in {report['total_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
