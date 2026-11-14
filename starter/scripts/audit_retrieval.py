"""Audit retrieved metadata against the source, and freeze grounding labels.

Two separate jobs, kept in one script because both read the same trace:

1. **Metadata correctness** (automatic). For every record in the 5 test questions
   x top-3 x 3 strategies, verify that `source`, `page`, `printed_page`,
   `page_type`, `article` and `form` actually describe the chunk text, by locating
   the chunk back in the normalized page and resolving the true article at that
   offset. This is a check against the source, not against our own output.

2. **Grounding labels** (manual). The 0/1/2 labels are supplied by the author
   from reading the retrieved text; the script only records and aggregates them.
   Automated matching is reported separately as Evidence Hit@3 and is never
   substituted for the manual label.

Run from starter/:  python scripts/audit_retrieval.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
RESULTS = STARTER / "results"

sys.path.insert(0, str(STARTER))

from src.chunking import (  # noqa: E402
    ARTICLE_HEADING,
    CHAPTER_HEADING,
    SECTION_HEADING,
    apply_structure,
)
from src.ingestion import load_pdf  # noqa: E402

PDF = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"
DOCUMENT_ID = "nghi-dinh-13-2023-nd-cp"
SOURCE = "data/nghi_dinh_13_2023_nd_cp.pdf"

BREADCRUMB = re.compile(r"^\[[^\]]*\]\n", re.MULTILINE)

# Manual grounding labels for the 5 test questions, per strategy:
# 0 = no evidence, 1 = evidence present but missing a needed condition/context,
# 2 = enough to answer and trace back.
GROUNDING = {
    "A_fixed": {
        "T01": (2, "top-1 chứa trọn khoản 10 Điều 9 về quyền yêu cầu bồi thường."),
        "T02": (1, "top-1 chứa khoản 2 Điều 16 nhưng bị cắt sau điểm b, thiếu điểm c 'đã được công khai' là điều kiện trả lời trực tiếp."),
        "T03": (1, "top-2 đúng trang 28 và có tiêu đề Điều 39 cùng khoản 1-2, nhưng thiếu khoản 5 'xóa, trả lại toàn bộ dữ liệu'."),
        "T04": (2, "top-1 chứa tiêu đề 'HỒ SƠ ĐÁNH GIÁ TÁC ĐỘNG CHUYỂN DỮ LIỆU CÁ NHÂN RA NƯỚC NGOÀI' của Mẫu số 06."),
        "T05": (2, "top-1 chứa khoản 7 Điều 25 nêu rõ 01 lần/năm kèm ngoại lệ."),
        "T06": (2, "top-1 chứa tiêu đề Điều 38 và khoản 2 về nhật ký hệ thống."),
    },
    "B_para": {
        "T01": (2, "top-1 chứa trọn khoản 10 Điều 9, có breadcrumb Điều 9 nên tự hiểu."),
        "T02": (2, "top-1 chứa trọn khoản 2 Điều 16 gồm cả điểm c 'đã được công khai' — đúng điều kiện cần."),
        "T03": (2, "top-1 chứa trọn Điều 39 gồm khoản 5 'xóa, trả lại toàn bộ dữ liệu', breadcrumb ghi Điều 39."),
        "T04": (2, "top-1 là Mẫu số 06 với tiêu đề hồ sơ chuyển dữ liệu ra nước ngoài."),
        "T05": (2, "top-1 chứa trọn khoản 7 Điều 25 về 01 lần/năm."),
        "T06": (2, "top-1 chứa Điều 38 và khoản 2 về nhật ký, breadcrumb Điều 38."),
    },
    "C_para_filter": {
        "T01": (2, "giống B: khoản 10 Điều 9 trọn vẹn."),
        "T02": (2, "giống B: khoản 2 Điều 16 trọn vẹn."),
        "T03": (2, "giống B: Điều 39 trọn vẹn, có khoản 5."),
        "T04": (2, "top-1 là Mẫu số 06; filter page_type loại hẳn trang quy định nên top-3 toàn biểu mẫu."),
        "T05": (2, "giống B: khoản 7 Điều 25 trọn vẹn."),
        "T06": (2, "top-1 Điều 38 khoản 2; filter article bảo đảm cả 3 kết quả thuộc Điều 38."),
    },
}


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def article_offsets(page) -> list[tuple[int, str]]:
    """Markers (char offset, article) for every 'Điều N.' heading inside a page."""
    markers: list[tuple[int, str]] = []
    offset = 0
    for paragraph in page.text.split("\n\n"):
        stripped = paragraph.strip()
        if stripped:
            match = ARTICLE_HEADING.match(stripped)
            if match:
                found = page.text.find(paragraph, offset)
                markers.append((found if found >= 0 else offset, f"Điều {match.group(1)}"))
        offset += len(paragraph) + 2
    return markers


def true_article(page, chunk_body: str, markers: list[tuple[int, str]]) -> tuple[str | None, str]:
    """Resolve the article that actually contains the start of the chunk body."""
    probe = chunk_body[:70]
    position = page.text.find(probe)
    if position < 0:
        return None, "chunk body not found in page text"

    current = page.metadata.get("article_at_start")
    for offset, article in markers:
        if offset <= position:
            current = article
        else:
            break
    return current, f"chunk starts at offset {position}"


def true_form(page, chunk_body: str) -> str | None:
    """A form page names its own template; the chunk can only be from that form."""
    declared = page.metadata.get("form")
    if not declared:
        return None
    return declared if declared in page.text else None


def main() -> int:
    traces = [json.loads(line) for line in (RESULTS / "retrieval_traces.jsonl").open(encoding="utf-8")]
    pages = apply_structure(load_pdf(PDF, DOCUMENT_ID, SOURCE))
    by_page = {page.page: page for page in pages}
    markers = {page.page: article_offsets(page) for page in pages}

    rows = []
    for trace in traces:
        if trace["split"] != "test":
            continue
        for item in trace["trace"]:
            page = by_page[item["page"]]
            body = BREADCRUMB.sub("", item["text"])
            expected_article, position_note = true_article(page, body, markers[item["page"]])

            checks = {
                "source_ok": item["source"] == page.source,
                "page_ok": fold(body[:80])[:40] in fold(page.text),
                "printed_page_ok": item["printed_page"] == page.metadata["printed_page"],
                "page_type_ok": item["page_type"] == page.metadata["page_type"],
                "article_ok": (item["article"] or None) == (expected_article or None),
                "form_ok": (item["form"] or None) == true_form(page, body),
            }
            rows.append(
                {
                    "strategy": trace["strategy"],
                    "question_id": trace["id"],
                    "rank": item["rank"],
                    "chunk_id": item["chunk_id"],
                    "page": item["page"],
                    "printed_page": item["printed_page"],
                    "metadata_article": item["article"] or "",
                    "true_article": expected_article or "",
                    "metadata_form": item["form"] or "",
                    "true_form": true_form(page, body) or "",
                    "page_type": item["page_type"],
                    "source_ok": checks["source_ok"],
                    "page_ok": checks["page_ok"],
                    "printed_page_ok": checks["printed_page_ok"],
                    "page_type_ok": checks["page_type_ok"],
                    "article_ok": checks["article_ok"],
                    "form_ok": checks["form_ok"],
                    "all_ok": all(checks.values()),
                    "note": position_note,
                    "hit": item["hit"],
                }
            )

    with (RESULTS / "metadata_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    grounding_rows = []
    for strategy, labels in GROUNDING.items():
        for question_id, (score, reason) in labels.items():
            grounding_rows.append(
                {
                    "strategy": strategy,
                    "question_id": question_id,
                    "grounding": score,
                    "reason": reason,
                }
            )
    with (RESULTS / "grounding_labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(grounding_rows[0].keys()))
        writer.writeheader()
        writer.writerows(grounding_rows)

    summary: dict = {"metadata": {}, "grounding": {}}
    for strategy in sorted({row["strategy"] for row in rows}):
        subset = [row for row in rows if row["strategy"] == strategy]
        summary["metadata"][strategy] = {
            "records": len(subset),
            "all_fields_ok": sum(1 for row in subset if row["all_ok"]),
            "page_ok": sum(1 for row in subset if row["page_ok"]),
            "printed_page_ok": sum(1 for row in subset if row["printed_page_ok"]),
            "page_type_ok": sum(1 for row in subset if row["page_type_ok"]),
            "article_ok": sum(1 for row in subset if row["article_ok"]),
            "form_ok": sum(1 for row in subset if row["form_ok"]),
            "article_errors": [
                {
                    "chunk_id": row["chunk_id"],
                    "metadata_article": row["metadata_article"],
                    "true_article": row["true_article"],
                }
                for row in subset
                if not row["article_ok"]
            ],
        }

    for strategy, labels in GROUNDING.items():
        scores = [score for score, _ in labels.values()]
        summary["grounding"][strategy] = {
            "n": len(scores),
            "count_0": scores.count(0),
            "count_1": scores.count(1),
            "count_2": scores.count(2),
            "mean": round(sum(scores) / len(scores), 2),
        }

    summary["notes"] = {
        "metadata_scope": "6 câu test x top-3 x 3 chiến lược = 54 bản ghi, đối chiếu với chính trang nguồn.",
        "article_check": (
            "Với mỗi chunk, tìm lại vị trí bắt đầu trong text trang rồi lấy Điều đang mở tại offset đó, "
            "thay vì tin vào nhãn đã lưu."
        ),
        "grounding_scorer": "tác giả (Đào Ngọc Hân) — tự chấm, có nguy cơ thiên lệch",
        "grounding_not_answer_accuracy": "Chỉ đánh giá evidence retrieval, không phải độ chính xác câu trả lời của LLM.",
    }
    (RESULTS / "audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"METADATA ({len({row['question_id'] for row in rows})} test x top-3):")
    for strategy, item in summary["metadata"].items():
        print(
            f"  {strategy:15s} all_ok {item['all_fields_ok']}/{item['records']}  "
            f"article {item['article_ok']}/{item['records']}  "
            f"page {item['page_ok']}/{item['records']}  form {item['form_ok']}/{item['records']}"
        )
        for error in item["article_errors"]:
            print(f"      article error {error['chunk_id']}: {error['metadata_article']} != {error['true_article']}")

    print(f"\nGROUNDING ({len(GROUNDING['A_fixed'])} test questions):")
    for strategy, item in summary["grounding"].items():
        print(
            f"  {strategy:15s} 0/1/2 = {item['count_0']}/{item['count_1']}/{item['count_2']}  "
            f"mean {item['mean']}/2"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
