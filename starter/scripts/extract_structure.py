"""Extract the documented structure (Chương / Mục / Điều) with page anchors.

Writes results/structure.json, used to pick gold pages for the benchmark and to
build the `chapter` / `article` metadata used by the metadata filter strategy.

Run from starter/:  python scripts/extract_structure.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.ingestion import load_pdf  # noqa: E402

PDF_PATH = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"
DOCUMENT_ID = "nghi-dinh-13-2023-nd-cp"
SOURCE = "data/nghi_dinh_13_2023_nd_cp.pdf"
RESULTS = STARTER / "results"

CHAPTER = re.compile(r"^Chương\s+([IVXLC]+)\s*$", re.MULTILINE)
SECTION = re.compile(r"^Mục\s+(\d+)\s*$", re.MULTILINE)
ARTICLE = re.compile(r"^Điều\s+(\d+)\.\s*(.+)$", re.MULTILINE)


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    pages = load_pdf(PDF_PATH, DOCUMENT_ID, SOURCE)

    chapters: list[dict] = []
    sections: list[dict] = []
    articles: list[dict] = []
    current_chapter: str | None = None
    current_section: str | None = None

    for page in pages:
        text = page.text
        events = []
        for match in CHAPTER.finditer(text):
            events.append((match.start(), "chapter", match.group(1)))
        for match in SECTION.finditer(text):
            events.append((match.start(), "section", match.group(1)))
        for match in ARTICLE.finditer(text):
            events.append((match.start(), "article", (match.group(1), match.group(2).strip())))
        events.sort(key=lambda item: item[0])

        for _, kind, value in events:
            if kind == "chapter":
                current_chapter = f"Chương {value}"
                chapters.append(
                    {"chapter": current_chapter, "physical_page": page.page,
                     "printed_page": page.metadata["printed_page"]}
                )
            elif kind == "section":
                current_section = f"Mục {value}"
                sections.append(
                    {"section": current_section, "chapter": current_chapter,
                     "physical_page": page.page, "printed_page": page.metadata["printed_page"]}
                )
            else:
                number, title = value
                articles.append(
                    {
                        "article": f"Điều {number}",
                        "article_number": int(number),
                        "title": title,
                        "chapter": current_chapter,
                        "section": current_section,
                        "physical_page": page.page,
                        "printed_page": page.metadata["printed_page"],
                    }
                )

    numbers = [article["article_number"] for article in articles]
    expected = list(range(1, len(numbers) + 1))
    structure = {
        "document_id": DOCUMENT_ID,
        "chapters": chapters,
        "sections": sections,
        "articles": articles,
        "article_count": len(articles),
        "articles_contiguous_from_1": numbers == expected,
        "missing_article_numbers": sorted(set(expected) - set(numbers)),
        "duplicate_article_numbers": sorted({n for n in numbers if numbers.count(n) > 1}),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "starter/scripts/extract_structure.py",
    }

    with (RESULTS / "structure.json").open("w", encoding="utf-8") as handle:
        json.dump(structure, handle, ensure_ascii=False, indent=2)

    print(f"chapters: {len(chapters)} -> {[c['chapter'] for c in chapters]}")
    print(f"sections: {len(sections)} -> {[s['section'] for s in sections]}")
    print(f"articles: {len(articles)} contiguous={structure['articles_contiguous_from_1']}")
    print(f"missing: {structure['missing_article_numbers']}")
    print(f"duplicates: {structure['duplicate_article_numbers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
