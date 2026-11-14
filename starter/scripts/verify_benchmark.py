"""Verify that every benchmark evidence string exists on its gold page.

The lab requires each evidence snippet to be checked against the normalized
source page, not just recalled from the PDF. This script loads the corpus
through the same pipeline the retriever will use, so a mismatch here means the
benchmark and the index disagree.

Checks per question:
  - gold page exists and is a content page
  - evidence substring is present on that page after normalization
  - filter value actually occurs in the corpus (article / page_type)
  - split counts meet the lab minimum (15 dev / 5 test)
  - test questions do not reuse a dev evidence string

Run from starter/:  python scripts/verify_benchmark.py
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
BENCHMARK = ROOT / "benchmark" / "questions.json"
RESULTS = STARTER / "results"
PDF = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"
DOCUMENT_ID = "nghi-dinh-13-2023-nd-cp"

MIN_DEV = 15
MIN_TEST = 5
MIN_TOTAL = 20
MIN_FILTER_QUESTIONS = 3
MIN_FILTER_TEST = 1

sys.path.insert(0, str(STARTER))

from src.ingestion import load_pdf  # noqa: E402


def fold(text: str) -> str:
    """Casefold and collapse whitespace so matching ignores formatting only."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    structure = json.loads((RESULTS / "structure.json").read_text(encoding="utf-8"))
    questions = benchmark["questions"]

    pages = load_pdf(PDF, DOCUMENT_ID, benchmark["document_id"])
    by_number = {page.page: page for page in pages}
    folded_pages = {page.page: fold(page.text) for page in pages}

    gold_pages = {article["article"]: article["physical_page"] for article in structure["articles"]}
    article_numbers = [article["article"] for article in structure["articles"]]

    ids = [item["id"] for item in questions]
    if len(ids) != len(set(ids)):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        problems.append(f"duplicate question ids: {duplicates}")

    dev = [item for item in questions if item["split"] == "dev"]
    test = [item for item in questions if item["split"] == "test"]
    if len(questions) < MIN_TOTAL:
        problems.append(f"total questions {len(questions)} < {MIN_TOTAL}")
    if len(dev) < MIN_DEV:
        problems.append(f"dev questions {len(dev)} < {MIN_DEV}")
    if len(test) < MIN_TEST:
        problems.append(f"test questions {len(test)} < {MIN_TEST}")

    filter_questions = [item for item in questions if item.get("filter")]
    filter_test = [item for item in filter_questions if item["split"] == "test"]
    if len(filter_questions) < MIN_FILTER_QUESTIONS:
        problems.append(f"filter questions {len(filter_questions)} < {MIN_FILTER_QUESTIONS}")
    if len(filter_test) < MIN_FILTER_TEST:
        problems.append(f"filter questions in test {len(filter_test)} < {MIN_FILTER_TEST}")

    dev_evidence = set()
    verified = 0
    for item in questions:
        qid = item["id"]
        if not item.get("answer"):
            problems.append(f"{qid}: missing answer")
        if not item.get("gold"):
            problems.append(f"{qid}: missing gold evidence")
            continue

        for gold in item["gold"]:
            page_no = gold["physical_page"]
            page = by_number.get(page_no)
            if page is None:
                problems.append(f"{qid}: physical_page {page_no} does not exist")
                continue
            if page.text.strip() == "":
                problems.append(f"{qid}: physical_page {page_no} has no text")
                continue
            if page.metadata["page_type"] != "noi_dung" and not item.get("filter", {}).get("page_type"):
                warnings.append(
                    f"{qid}: gold page {page_no} is {page.metadata['page_type']} "
                    "but the question has no page_type filter"
                )

            evidence = fold(gold["evidence"])
            if evidence not in folded_pages[page_no]:
                problems.append(
                    f"{qid}: evidence not found on physical_page {page_no} "
                    f"({len(gold['evidence'])} chars): {gold['evidence'][:70]!r}"
                )
                continue
            verified += 1

            printed = gold.get("printed_page")
            actual_printed = page.metadata["printed_page"]
            if printed is not None and printed != actual_printed:
                problems.append(
                    f"{qid}: printed_page {printed} != actual {actual_printed} for page {page_no}"
                )

            article = gold.get("article", "")
            if article.startswith("Điều "):
                if article not in article_numbers:
                    problems.append(f"{qid}: article {article} not in structure.json")
                elif gold_pages[article]:
                    first_page = gold_pages[article]
                    if first_page > page_no:
                        problems.append(
                            f"{qid}: article {article} starts on page {first_page}, "
                            f"after gold page {page_no}"
                        )

        if item["split"] == "dev":
            for gold in item["gold"]:
                dev_evidence.add(fold(gold["evidence"]))

    for item in test:
        for gold in item["gold"]:
            if fold(gold["evidence"]) in dev_evidence:
                problems.append(f"{item['id']}: test evidence reused from a dev question")

    for item in filter_questions:
        for field, value in item["filter"].items():
            if field == "article":
                if value not in article_numbers:
                    problems.append(f"{item['id']}: filter article {value} not in structure.json")
            elif field == "page_type":
                valid = {"noi_dung", "phu_luc_bieu_mau", "phu_luc_muc_luc"}
                if value not in valid:
                    problems.append(f"{item['id']}: filter page_type {value} not in {sorted(valid)}")
                elif not any(p.metadata["page_type"] == value for p in pages):
                    problems.append(f"{item['id']}: no page has page_type {value}")
            else:
                warnings.append(f"{item['id']}: filter field {field} is not checked by this script")

    report = {
        "benchmark_id": benchmark["benchmark_version"],
        "total_questions": len(questions),
        "dev": len(dev),
        "test": len(test),
        "filter_questions": len(filter_questions),
        "filter_questions_test": len(filter_test),
        "gold_entries": sum(len(item["gold"]) for item in questions),
        "evidence_verified": verified,
        "problems": problems,
        "warnings": warnings,
        "generator": "starter/scripts/verify_benchmark.py",
    }
    (RESULTS / "benchmark_check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for problem in problems:
        print(f"FAIL: {problem}")
    for warning in warnings:
        print(f"WARN: {warning}")

    if problems:
        print(f"\n{len(problems)} problem(s) found")
        return 1

    print("benchmark OK")
    print(f"  questions      {len(questions)} ({len(dev)} dev / {len(test)} test)")
    print(f"  filter         {len(filter_questions)} total, {len(filter_test)} in test")
    print(f"  evidence       {verified}/{sum(len(item['gold']) for item in questions)} verified on gold page")
    print(f"  warnings       {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
