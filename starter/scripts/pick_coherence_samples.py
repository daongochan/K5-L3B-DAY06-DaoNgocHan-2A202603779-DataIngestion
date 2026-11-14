"""Freeze the 10 coherence sample positions before any chunk is scored.

GUIDE requires the positions to be fixed before looking at labels, so this
script only *selects* them deterministically from the corpus and records the
source paragraph at each position. Scores are added later by hand in
results/coherence_labels.csv; this script never assigns a score.

Selection rule (published, deterministic): the first 10 content pages in physical
order, and on each page the paragraph that contains the most characters. Ties go
to the earliest paragraph.

Run from starter/:  python scripts/pick_coherence_samples.py
"""
from __future__ import annotations

import csv
import json
import sys
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

SAMPLE_PAGES = 10
FIXED_SIZE = 500
FIXED_OVERLAP = 150
PARA_MAX = 700


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    pages = apply_structure(load_pdf(PDF, DOCUMENT_ID, SOURCE))
    content = [page for page in pages if page.metadata["page_type"] != "phu_luc_muc_luc"]
    selected = content[:SAMPLE_PAGES]

    rows = []
    for page in selected:
        paragraphs = [part.strip() for part in page.text.split("\n\n") if part.strip()]
        if not paragraphs:
            continue
        # Longest paragraph: the position most likely to expose a bad split.
        index, best = max(
            enumerate(paragraphs), key=lambda item: (len(item[1]), -item[0])
        )

        chunks_a = fixed_size(page, FIXED_SIZE, FIXED_OVERLAP)
        chunks_b = by_paragraph(page, PARA_MAX)

        def covering(chunks):
            found = []
            for chunk in chunks:
                if best[:80] and best[:80] in chunk.text:
                    found.append(chunk.chunk_id)
                elif best[-80:] and best[-80:] in chunk.text:
                    found.append(chunk.chunk_id)
            return found

        rows.append(
            {
                "sample_id": f"C{len(rows) + 1:02d}",
                "physical_page": page.page,
                "printed_page": page.metadata["printed_page"],
                "article": page.metadata.get("article_at_start"),
                "paragraph_index": index,
                "paragraph_chars": len(best),
                "source_paragraph": best,
                "chunks_A_covering": ";".join(covering(chunks_a)),
                "chunks_B_covering": ";".join(covering(chunks_b)),
                "score_A": "",
                "reason_A": "",
                "score_B": "",
                "reason_B": "",
            }
        )

    out = RESULTS / "coherence_samples.csv"

    # Re-running must not destroy hand-entered labels: the positions are frozen,
    # so any existing score for the same sample_id is still valid.
    existing: dict[str, dict] = {}
    if out.exists():
        with out.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                existing[row.get("sample_id", "")] = row

    for row in rows:
        previous = existing.get(row["sample_id"])
        if previous:
            for key in ("score_A", "reason_A", "score_B", "reason_B"):
                if previous.get(key):
                    row[key] = previous[key]

    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    meta = {
        "selection_rule": (
            "10 trang nội dung đầu tiên theo thứ tự vật lý; trên mỗi trang chọn "
            "đoạn có nhiều ký tự nhất (hòa thì lấy đoạn sớm hơn)."
        ),
        "frozen_before_scoring": True,
        "sample_count": len(rows),
        "samples": [
            {
                "sample_id": row["sample_id"],
                "physical_page": row["physical_page"],
                "printed_page": row["printed_page"],
                "paragraph_chars": row["paragraph_chars"],
            }
            for row in rows
        ],
        "scoring": "0 = cắt giữa ý/thiếu chủ thể; 1 = hiểu một phần; 2 = tự hiểu được, trọn ý.",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/pick_coherence_samples.py",
    }
    (RESULTS / "coherence_samples.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"samples: {len(rows)} -> results/coherence_samples.csv")
    for row in rows:
        print(
            f"  {row['sample_id']} p{row['physical_page']:02d} "
            f"{row['paragraph_chars']:3d} chars | A:{row['chunks_A_covering'] or '-'} "
            f"B:{row['chunks_B_covering'] or '-'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
