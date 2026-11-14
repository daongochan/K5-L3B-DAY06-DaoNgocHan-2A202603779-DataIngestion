"""Export both chunk configurations and their statistics.

This is the checkpoint artifact for "Đọc, chuẩn hóa và thử chunk": it proves two
chunking configurations can be produced from the same corpus, that every chunk
keeps a page back-reference, and that nothing was silently dropped.

Outputs (starter/results/):
  chunks_A_fixed.jsonl     strategy A: fixed 500 chars, 150 overlap
  chunks_B_para.jsonl      strategy B: paragraph-aligned, 700 char budget
  chunk_stats.json         counts, length distribution, coverage checks

Run from starter/:  python scripts/export_chunks.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.chunking import apply_structure, by_paragraph, fixed_size  # noqa: E402
from src.ingestion import load_pdf  # noqa: E402

PDF = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"
DOCUMENT_ID = "nghi-dinh-13-2023-nd-cp"
SOURCE = "data/nghi_dinh_13_2023_nd_cp.pdf"
RESULTS = STARTER / "results"

# A: fixed window. 500 characters holds a whole clause plus its context while
# staying well under typical embedding input limits.
#
# Overlap was chosen on dev only, by measuring how much benchmark evidence
# survives whole inside some chunk (scripts/check_chunk_coverage.py):
#   50  -> dev 13/16, 6 evidence strings destroyed at a window boundary
#   100 -> dev 15/16
#   150 -> dev 16/16 (199 chunks)
#   200 -> dev 16/16 (222 chunks, more storage for no gain)
# 150 is the smallest overlap that loses nothing on dev; 140-160 all score the
# same, so the choice is not a knife-edge fit.
FIXED_SIZE = 500
FIXED_OVERLAP = 150

# B: paragraph-aligned. ~700 characters matches the average length of an
# article on this corpus and keeps the number of chunks close to A, so the A/B
# comparison is not confounded by a large difference in index size.
PARA_MAX = 700


def dump(path: Path, chunks: list) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "source": chunk.source,
                        "page": chunk.page,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def describe(
    name: str, chunks: list, pages_used: set[int], expected_pages: list[int]
) -> dict:
    lengths = [len(chunk.text) for chunk in chunks]
    bodies = [chunk.metadata.get("body_char_count", len(chunk.text)) for chunk in chunks]
    articles = Counter(chunk.metadata.get("article") for chunk in chunks)
    return {
        "strategy": name,
        "chunks": len(chunks),
        "chars_total": sum(lengths),
        "chars_mean": round(statistics.mean(lengths), 1),
        "chars_median": statistics.median(lengths),
        "chars_min": min(lengths),
        "chars_max": max(lengths),
        "chars_stdev": round(statistics.stdev(lengths), 1) if len(lengths) > 1 else 0.0,
        "body_chars_mean": round(statistics.mean(bodies), 1),
        "chunks_under_100_chars": sum(1 for length in lengths if length < 100),
        "pages_covered": len(pages_used),
        "pages_expected": len(expected_pages),
        "pages_missing": sorted(set(expected_pages) - pages_used),
        "distinct_articles": len([key for key in articles if key]),
        "chunks_without_article": sum(1 for chunk in chunks if not chunk.metadata.get("article")),
        "chunks_without_page": sum(1 for chunk in chunks if not chunk.page),
        "chunks_without_source": sum(1 for chunk in chunks if not chunk.source),
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    pages = apply_structure(load_pdf(PDF, DOCUMENT_ID, SOURCE))
    content_pages = [page for page in pages if page.metadata["page_type"] != "phu_luc_muc_luc"]

    chunks_a = [
        chunk
        for page in content_pages
        for chunk in fixed_size(page, FIXED_SIZE, FIXED_OVERLAP)
    ]
    chunks_b = [chunk for page in content_pages for chunk in by_paragraph(page, PARA_MAX)]

    dump(RESULTS / "chunks_A_fixed.jsonl", chunks_a)
    dump(RESULTS / "chunks_B_para.jsonl", chunks_b)

    # The appendix index page is excluded from the corpus, so it is also
    # excluded from the coverage expectation instead of being reported missing.
    expected_pages = [page.page for page in content_pages]
    stats_a = describe("A_fixed", chunks_a, {chunk.page for chunk in chunks_a}, expected_pages)
    stats_b = describe("B_para", chunks_b, {chunk.page for chunk in chunks_b}, expected_pages)

    stats = {
        "document_id": DOCUMENT_ID,
        "corpus_sha256": json.loads(
            (RESULTS / "page_audit.json").read_text(encoding="utf-8")
        )["sha256"],
        "parameters": {
            "A_fixed": {"size": FIXED_SIZE, "overlap": FIXED_OVERLAP},
            "B_para": {"max_size": PARA_MAX, "breadcrumb": True, "heading_aligned": True},
        },
        "parameter_rationale": {
            "A_fixed": "500 ký tự chứa trọn một khoản kèm ngữ cảnh; overlap 150 (30%) là mức nhỏ nhất không làm mất evidence nào trên dev (50 → 13/16; 100 → 15/16; 150 → 16/16; 200 → 16/16 nhưng thêm 23 chunk mà không thêm lợi ích).",
            "B_para": "700 ký tự xấp xỉ độ dài trung bình của một điều trong corpus này, giữ số chunk gần A để so sánh A–B không bị nhiễu bởi chênh lệch kích thước index.",
            "comparison": "A–B chỉ khác cách chunk; model, store, metric, corpus và benchmark giữ nguyên.",
        },
        "excluded_pages": [page.page for page in pages if page.metadata["page_type"] == "phu_luc_muc_luc"],
        "strategies": {"A_fixed": stats_a, "B_para": stats_b},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/export_chunks.py",
    }
    (RESULTS / "chunk_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for name in ("A_fixed", "B_para"):
        item = stats["strategies"][name]
        print(
            f"{name}: chunks={item['chunks']} chars avg={item['chars_mean']} "
            f"min={item['chars_min']} max={item['chars_max']} "
            f"pages={item['pages_covered']}/{item['pages_expected']} "
            f"articles={item['distinct_articles']}"
        )

    problems = []
    for name, item in stats["strategies"].items():
        if item["chunks_without_page"] or item["chunks_without_source"]:
            problems.append(f"{name}: chunk missing page or source")
        if item["pages_missing"]:
            problems.append(f"{name}: pages with no chunk: {item['pages_missing']}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1

    print("chunks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
