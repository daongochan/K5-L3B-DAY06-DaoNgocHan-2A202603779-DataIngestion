"""Read and normalize source data while keeping page-level traceability."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

# Running header printed on every Công báo page, e.g.
# "CÔNG BÁO/Số 685 + 686/Ngày 30-4-2023 3". It repeats the issue and the
# printed page number, so it is removed from the body and the number is kept
# as metadata instead.
RUNNING_HEADER = re.compile(
    r"CÔNG\s*BÁO\s*/\s*Số\s*\d+\s*\+\s*\d+\s*/\s*Ngày\s*\d{1,2}-\d{1,2}-\d{4}",
    re.IGNORECASE,
)

HORIZONTAL_SPACE = re.compile(r"[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]+")
# Two or more spaces encode the gap between visual columns (letterhead, signature
# blocks, form labels). The gap must stay a boundary, otherwise unrelated cells
# fuse into one sentence ("CHÍNH PHỦ CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM").
COLUMN_GAP = re.compile(r"[ \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]{2,}")
# Column cells are joined with a sentinel during normalization and turned back
# into real line breaks at the end, so a column gap survives the paragraph merge
# without being treated as a paragraph boundary of its own.
COLUMN_SEPARATOR = "\u0000"
INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TRAILING_HYPHEN = re.compile(r"(\w)-$")

# "Phụ lục" opens the appendix; everything from that page onward is a form.
APPENDIX_OPENING = re.compile(r"^Phụ lục$", re.MULTILINE | re.IGNORECASE)

PAGE_TYPE_MAIN = "noi_dung"
PAGE_TYPE_APPENDIX_INDEX = "phu_luc_muc_luc"
PAGE_TYPE_APPENDIX_FORM = "phu_luc_bieu_mau"


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace, then restore paragraph boundaries.

    The PDF wraps every paragraph at a fixed width: a new paragraph starts on an
    indented line, while wrapped continuation lines start at the left margin.
    That indentation is the only paragraph signal available, so it is used to
    rejoin wrapped lines and emit one blank line between paragraphs.

    Visual columns are kept apart: a run of two or more horizontal spaces marks a
    column gap, and each cell stays on its own line instead of being fused into
    one sentence ("CHÍNH PHỦ" next to "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM").
    """
    text = unicodedata.normalize("NFC", text)
    text = text.translate(INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL.sub("", text)

    paragraphs: list[list[str]] = []
    current: list[str] = []
    previous_blank = True

    for raw_line in text.split("\n"):
        expanded = raw_line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(" "))
        cells = [cell for cell in COLUMN_GAP.split(expanded.strip()) if cell.strip()]
        if not cells:
            previous_blank = True
            continue
        line = HORIZONTAL_SPACE.sub(" ", COLUMN_SEPARATOR.join(cells)).strip()

        continues = indent == 0 and not previous_blank and current
        if continues:
            last = current[-1]
            joiner = "" if TRAILING_HYPHEN.search(last) else " "
            current[-1] = f"{last}{joiner}{line}"
        else:
            if current:
                paragraphs.append(current)
            current = [line]
        previous_blank = False

    if current:
        paragraphs.append(current)

    joined = "\n\n".join(" ".join(paragraph) for paragraph in paragraphs).strip()
    return joined.replace(COLUMN_SEPARATOR, "\n")


def _printed_page(header_match: re.Match[str], line: str) -> int | None:
    """Read the page number the Công báo prints beside its running header.

    Takes the already-matched header so the same line is not searched twice.
    """
    for segment in (line[: header_match.start()], line[header_match.end():]):
        for value in re.findall(r"\d+", segment):
            number = int(value)
            if 1 <= number <= 999:
                return number
    return None


def strip_running_header(raw_text: str) -> tuple[str, int | None]:
    """Drop the full running-header line, page number included.

    The header and the printed page number share one physical line
    (".../Ngày 30-4-2023 39"). Removing only the header would leave "39" behind
    as if it were body text, so the whole line is removed instead.
    """
    printed_page = None
    kept: list[str] = []
    for line in raw_text.split("\n"):
        header_match = RUNNING_HEADER.search(line)
        if header_match:
            if printed_page is None:
                printed_page = _printed_page(header_match, line)
            continue
        kept.append(line)
    return "\n".join(kept), printed_page


def appendix_start_page(texts: list[str]) -> int | None:
    """Return the 1-based physical page where the "Phụ lục" appendix starts.

    Page type has to be decided from document position, not from words like
    "Mẫu số": the main body itself cites "Mẫu số 01, 02" when it tells readers
    which form to submit, so a content regex would mislabel body pages.
    """
    for index, text in enumerate(texts, start=1):
        if APPENDIX_OPENING.search(text):
            return index
    return None


def _page_type(physical_page: int, appendix_start: int | None) -> str:
    if appendix_start is None or physical_page < appendix_start:
        return PAGE_TYPE_MAIN
    if physical_page == appendix_start:
        return PAGE_TYPE_APPENDIX_INDEX
    return PAGE_TYPE_APPENDIX_FORM


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract one DocumentPage per physical PDF page.

    Text is extracted in ``layout`` mode, which reconstructs accented Vietnamese
    syllables correctly. The default mode of this PDF splits words at tone marks
    ("d ữ li ệu"), so it is only used as a recorded fallback.
    """
    path = Path(path)
    reader = PdfReader(str(path))
    extracted: list[dict] = []

    for index, raw_page in enumerate(reader.pages, start=1):
        warnings: list[str] = []
        try:
            raw_text = raw_page.extract_text(extraction_mode="layout") or ""
            mode = "layout"
        except Exception as exc:  # pragma: no cover - depends on the PDF
            raw_text = raw_page.extract_text() or ""
            mode = "plain"
            warnings.append(f"layout extraction failed, used plain mode: {exc}")

        header_found = bool(RUNNING_HEADER.search(raw_text))
        body_text, printed_page = strip_running_header(raw_text)
        if not header_found:
            warnings.append("running header not found: printed page number unknown")
        if not body_text.strip():
            warnings.append("page has no extractable text")

        extracted.append(
            {
                "page": index,
                "printed_page": printed_page,
                "text": normalize_text(body_text),
                "mode": mode,
                "warnings": warnings,
            }
        )

    appendix_start = appendix_start_page([item["text"] for item in extracted])

    pages: list[DocumentPage] = []
    for item in extracted:
        text = item["text"]
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=item["page"],
                text=text,
                metadata={
                    "printed_page": item["printed_page"],
                    "page_type": _page_type(item["page"], appendix_start),
                    "char_count": len(text),
                    "word_count": len(text.split()),
                    "paragraph_count": text.count("\n\n") + 1 if text else 0,
                    "extraction_mode": item["mode"],
                    "warnings": item["warnings"],
                },
            )
        )

    return pages
