"""Audit corpus extraction: one row per physical PDF page.

Writes machine-readable evidence used by the manifest and the report:
  results/page_audit.csv   per-page chars, words, printed page, type, warnings
  results/page_audit.json  totals plus the pages accepted as content pages
  results/ingest.log       console log of the same run

Run from starter/:  python scripts/audit_pages.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.ingestion import (  # noqa: E402
    PAGE_TYPE_APPENDIX_FORM,
    PAGE_TYPE_APPENDIX_INDEX,
    PAGE_TYPE_MAIN,
    load_pdf,
)

PDF_PATH = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"
DOCUMENT_ID = "nghi-dinh-13-2023-nd-cp"
SOURCE = "data/nghi_dinh_13_2023_nd_cp.pdf"
RESULTS = STARTER / "results"

# A page counts as content when it carries at least this many non-whitespace
# characters after normalization and is not the appendix index.
MIN_CONTENT_CHARS = 500

# Lab requirement: at least 30 pages of useful content.
REQUIRED_CONTENT_PAGES = 30

DOT_RUN = re.compile(r"\.{4,}|\u2026{2,}")


def body_chars(text: str) -> int:
    """Non-whitespace characters, dots of fill-in forms included."""
    return len(re.sub(r"\s", "", text))


def text_chars(text: str) -> int:
    """Non-whitespace characters with dotted form fillers removed."""
    return len(re.sub(r"\s", "", DOT_RUN.sub("", text)))


def classify(page, body: int) -> tuple[bool, bool, str]:
    """Return (counted_as_content, filler_heavy, exclusion_reason)."""
    if page.metadata["page_type"] == PAGE_TYPE_APPENDIX_INDEX:
        return False, False, "muc_luc_phu_luc"
    if body < MIN_CONTENT_CHARS:
        return False, False, f"duoi_nguong_{MIN_CONTENT_CHARS}_ky_tu"
    filler_heavy = text_chars(page.text) < 0.4 * body
    return True, filler_heavy, ""


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []

    def log(message: str) -> None:
        print(message)
        log_lines.append(message)

    raw = PDF_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    log(f"file: {PDF_PATH.relative_to(STARTER).as_posix()}")
    log(f"sha256: {digest}  bytes: {len(raw)}")
    log(f"started_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    pages = load_pdf(PDF_PATH, DOCUMENT_ID, SOURCE)
    log(f"physical pages: {len(pages)}")

    rows = []
    accepted: list[int] = []
    excluded: list[dict] = []
    filler_pages: list[int] = []
    total_warnings = 0

    for page in pages:
        body = body_chars(page.text)
        plain = text_chars(page.text)
        included, filler_heavy, reason = classify(page, body)
        warnings = page.metadata["warnings"]
        total_warnings += len(warnings)
        rows.append(
            {
                "physical_page": page.page,
                "printed_page": page.metadata["printed_page"],
                "page_type": page.metadata["page_type"],
                "chars_total": page.metadata["char_count"],
                "chars_body": body,
                "chars_without_filler": plain,
                "words": page.metadata["word_count"],
                "paragraphs": page.metadata["paragraph_count"],
                "extraction_mode": page.metadata["extraction_mode"],
                "counted_as_content": included,
                "filler_heavy": filler_heavy,
                "exclusion_reason": reason,
                "warnings": " | ".join(warnings),
                "first_line": page.text.split("\n", 1)[0][:80] if page.text else "",
            }
        )
        if included:
            accepted.append(page.page)
            if filler_heavy:
                filler_pages.append(page.page)
        else:
            excluded.append({"physical_page": page.page, "reason": reason})
        if warnings:
            log(f"p{page.page:02d} WARN {'; '.join(warnings)}")

    with (RESULTS / "page_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    main_body_chars = sum(row["chars_body"] for row in rows if row["page_type"] == PAGE_TYPE_MAIN)
    appendix_chars = sum(
        row["chars_body"] for row in rows if row["page_type"] == PAGE_TYPE_APPENDIX_FORM
    )

    summary = {
        "document_id": DOCUMENT_ID,
        "source": SOURCE,
        "sha256": digest,
        "bytes": len(raw),
        "physical_pages": len(pages),
        "content_pages": len(accepted),
        "content_page_numbers": accepted,
        "excluded_pages": excluded,
        "filler_heavy_pages": filler_pages,
        "chars_body_content_pages": sum(row["chars_body"] for row in rows if row["counted_as_content"]),
        "chars_all_pages": sum(row["chars_body"] for row in rows),
        "main_body_chars": main_body_chars,
        "appendix_chars": appendix_chars,
        "chars_with_whitespace_all_pages": sum(row["chars_total"] for row in rows),
        "page_type_counts": {
            kind: sum(1 for row in rows if row["page_type"] == kind)
            for kind in (PAGE_TYPE_MAIN, PAGE_TYPE_APPENDIX_INDEX, PAGE_TYPE_APPENDIX_FORM)
        },
        "pages_with_warnings": sum(1 for row in rows if row["warnings"]),
        "total_warnings": total_warnings,
        "min_content_chars": MIN_CONTENT_CHARS,
        "required_content_pages": REQUIRED_CONTENT_PAGES,
        "meets_required_content_pages": len(accepted) >= REQUIRED_CONTENT_PAGES,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/audit_pages.py",
    }

    with (RESULTS / "page_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    log("")
    log(f"content pages: {len(accepted)}/{len(pages)}  {accepted}")
    log(f"excluded: {excluded}")
    log(f"filler-heavy pages: {filler_pages}")
    log(f"body chars on content pages: {summary['chars_body_content_pages']}")
    log(f"pages with warnings: {summary['pages_with_warnings']} "
        f"(total warnings: {summary['total_warnings']})")
    status = "OK" if len(accepted) >= REQUIRED_CONTENT_PAGES else "FAIL"
    log(f"requirement >= {REQUIRED_CONTENT_PAGES} content pages: {status}")
    log(f"finished_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    (RESULTS / "ingest.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
