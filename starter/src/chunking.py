"""Chunking strategies with source traceability.

Two strategies are implemented, matching the lab's A/B comparison:

  fixed_size    A: blind character windows of a fixed size with overlap.
  by_paragraph  B: heading-aligned groups of whole paragraphs, never splitting a
                   paragraph unless it alone exceeds the budget, and prefixed
                   with a chapter/article breadcrumb so a chunk is understandable
                   on its own.

Both keep ``document_id``, ``source`` and ``page`` on every chunk, and carry the
filter fields derived from the document structure (``page_type``, ``article``,
``chapter``, ``section``).
"""
from __future__ import annotations

import re

from .models import Chunk, DocumentPage

PAGE_TYPE_MAIN = "noi_dung"

ARTICLE_HEADING = re.compile(r"^Điều\s+(\d+)\.\s*(.+)$")
CHAPTER_HEADING = re.compile(r"^Chương\s+([IVXLC]+)$")
SECTION_HEADING = re.compile(r"^Mục\s+(\d+)$")
FORM_HEADING = re.compile(r"^Mẫu số\s*(\d+)\s*$", re.MULTILINE)
SENTENCE_END = re.compile(r"(?<=[.;:])\s+")

# A fixed-size window may move its end back this far to avoid cutting a word.
# Beyond this the window stays exactly `size` characters.
WORD_SNAP = 40

STRATEGY_FIXED = "A_fixed"
STRATEGY_PARAGRAPH = "B_para"


def _chunk_id(document_id: str, page: int, strategy: str, index: int) -> str:
    return f"{document_id}:p{page:03d}:{strategy}:{index:03d}"


def _base_metadata(page: DocumentPage, strategy: str) -> dict:
    """Metadata every chunk inherits, so any hit can be traced back to a page."""
    return {
        "document_id": page.document_id,
        "source": page.source,
        "page": page.page,
        "physical_page": page.page,
        "printed_page": page.metadata.get("printed_page"),
        "page_type": page.metadata.get("page_type"),
        "form": page.metadata.get("form"),
        "strategy": strategy,
    }


def apply_structure(pages: list[DocumentPage]) -> list[DocumentPage]:
    """Record which article/chapter is open at the top of each page.

    Articles routinely continue onto the following page, and one page can open
    several articles. The state therefore has to be carried from page to page
    instead of being read off a single page in isolation.

    The appendix is *not* part of the decree's article structure: its forms are
    numbered "Mẫu số 01".."Mẫu số 06". Carrying "Điều 44" into the appendix would
    label Mẫu số 01 as part of Điều 44 and make an ``article`` filter return form
    pages when it was meant to restrict to a decree article. State is therefore
    cleared as soon as a non-body page starts, and form pages get their own
    ``form`` value.
    """
    article = article_title = chapter = section = None

    for page in pages:
        if page.metadata.get("page_type") != PAGE_TYPE_MAIN:
            # Appendix: the decree's chapter/article state does not apply here.
            article = article_title = chapter = section = None

        page.metadata["article_at_start"] = article
        page.metadata["article_title_at_start"] = article_title
        page.metadata["chapter_at_start"] = chapter
        page.metadata["section_at_start"] = section

        if page.metadata.get("page_type") != PAGE_TYPE_MAIN:
            form = FORM_HEADING.match(page.text)
            if form:
                page.metadata["form"] = f"Mẫu số {form.group(1)}"
            continue

        for paragraph in page.text.split("\n\n"):
            line = paragraph.strip()
            if not line:
                continue
            chapter_match = CHAPTER_HEADING.match(line)
            if chapter_match:
                chapter = f"Chương {chapter_match.group(1)}"
                continue
            section_match = SECTION_HEADING.match(line)
            if section_match:
                section = f"Mục {section_match.group(1)}"
                continue
            article_match = ARTICLE_HEADING.match(line)
            if article_match:
                article = f"Điều {article_match.group(1)}"
                article_title = article_match.group(2).strip()

    return pages


def _breadcrumb(state: dict, body_has_article_heading: bool) -> str:
    """Build the context prefix for a chunk.

    Only the context the chunk does not already state is included: if the chunk
    opens with its own "Điều N." heading, repeating it in the breadcrumb would
    duplicate the same words in the embedded text.
    """
    parts = [value for value in (state.get("chapter"), state.get("section")) if value]
    article = state.get("article")
    if article and not body_has_article_heading:
        title = state.get("article_title")
        parts.append(f"{article}. {title}" if title else article)
    return " > ".join(parts)


def article_markers(page: DocumentPage) -> list[tuple[int, str, str | None]]:
    """Char offset of every article heading in the page, with its title.

    A page can open with one article and start several others, so the article a
    chunk belongs to depends on where the chunk starts, not on which article was
    open at the top of the page.
    """
    markers: list[tuple[int, str, str | None]] = []
    offset = 0
    for paragraph in page.text.split("\n\n"):
        stripped = paragraph.strip()
        if stripped:
            match = ARTICLE_HEADING.match(stripped)
            if match:
                position = page.text.find(paragraph, offset)
                if position < 0:
                    position = offset
                markers.append(
                    (position, f"Điều {match.group(1)}", match.group(2).strip())
                )
        offset += len(paragraph) + 2
    return markers


def article_at(page: DocumentPage, offset: int, markers: list[tuple[int, str, str | None]]) -> str | None:
    """Article whose heading is the last one at or before ``offset``."""
    current = page.metadata.get("article_at_start")
    for position, article, _ in markers:
        if position <= offset:
            current = article
        else:
            break
    return current


def fixed_size(
    page: DocumentPage,
    size: int,
    overlap: int,
    strategy: str = STRATEGY_FIXED,
) -> list[Chunk]:
    """Split one page into overlapping character windows.

    The window end is pulled back to the nearest whitespace when that is within
    ``WORD_SNAP`` characters, so a chunk does not end mid-word. The next window
    starts ``overlap`` characters before the previous end, which is what creates
    the overlap.

    ``article`` is resolved from the window's own start offset, because a single
    page can contain several articles. Labelling every window with the article
    open at the top of the page would be wrong for any window that starts after a
    later "Điều N." heading.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and smaller than size")

    text = page.text
    if not text.strip():
        return []

    base = _base_metadata(page, strategy)
    markers = article_markers(page)
    chunks: list[Chunk] = []
    start = 0
    index = 0
    length = len(text)

    while start < length:
        end = min(start + size, length)
        if end < length:
            space = text.rfind(" ", start, end)
            if space > start and end - space <= WORD_SNAP:
                end = space

        piece = text[start:end].strip()
        if piece:
            metadata = dict(base)
            metadata.update(
                {
                    "chunk_index": index,
                    "char_count": len(piece),
                    "start_offset": start,
                    "end_offset": end,
                    "article": article_at(page, start, markers),
                    "chapter": page.metadata.get("chapter_at_start"),
                }
            )
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(page.document_id, page.page, strategy, index),
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=piece,
                    metadata=metadata,
                )
            )
            index += 1

        if end >= length:
            break
        # Guard the step: snapping the window end backwards can otherwise make
        # `end - overlap` fall before `start` and loop forever.
        start = max(start + 1, end - overlap)

    return chunks


def _split_long_paragraph(paragraph: str, max_size: int) -> list[str]:
    """Split a paragraph that alone exceeds the budget, preferring sentence ends."""
    if len(paragraph) <= max_size:
        return [paragraph]

    pieces: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(paragraph):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_size:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(sentence) > max_size:
            pieces.append(sentence[:max_size])
            sentence = sentence[max_size:]
        current = sentence
    if current:
        pieces.append(current)
    return pieces


def _is_heading_only(group: list[str]) -> bool:
    """True when every paragraph in the group is just a chapter/section heading.

    A heading line such as "Chương IV" carries no answerable content on its own,
    so it must not become a retrievable chunk.
    """
    for paragraph in group:
        lines = [line for line in paragraph.split("\n") if line.strip()]
        if not lines:
            continue
        if not (CHAPTER_HEADING.match(lines[0]) or SECTION_HEADING.match(lines[0])):
            return False
    return bool(group)


def _is_uppercase_title(paragraph: str) -> bool:
    """True for a short all-caps title line that belongs to a heading above it.

    The decree prints "Chương IV" followed by "ĐIỀU KHOẢN THI HÀNH" on separate
    lines. Once the chapter line is dropped, the title alone would become a
    content-free chunk, so it is dropped too.
    """
    text = " ".join(paragraph.split())
    if not text or len(text) > 90:
        return False
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def by_paragraph(
    page: DocumentPage,
    max_size: int,
    strategy: str = STRATEGY_PARAGRAPH,
    include_breadcrumb: bool = True,
) -> list[Chunk]:
    """Group whole paragraphs into chunks of at most ``max_size`` characters.

    A chapter, section or article heading always starts a new chunk, so a chunk
    never mixes two articles. That alignment is what makes the ``article`` filter
    meaningful. A single paragraph longer than the budget is split at sentence
    boundaries rather than dropped.

    ``max_size`` limits the body; the breadcrumb prefix is added on top, so the
    stored text can be slightly longer.
    """
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    paragraphs = [part.strip() for part in page.text.split("\n\n") if part.strip()]
    if not paragraphs:
        return []

    state = {
        "article": page.metadata.get("article_at_start"),
        "article_title": page.metadata.get("article_title_at_start"),
        "chapter": page.metadata.get("chapter_at_start"),
        "section": page.metadata.get("section_at_start"),
    }

    base = _base_metadata(page, strategy)
    groups: list[tuple[list[str], dict]] = []
    current: list[str] = []
    current_state = dict(state)
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        if current:
            groups.append((current, dict(current_state)))
        current = []
        current_length = 0

    skip_titles = False
    for paragraph in paragraphs:
        heading = None
        chapter_match = CHAPTER_HEADING.match(paragraph)
        section_match = SECTION_HEADING.match(paragraph)
        article_match = ARTICLE_HEADING.match(paragraph)

        if chapter_match:
            state["chapter"] = f"Chương {chapter_match.group(1)}"
            heading = "chapter"
        elif section_match:
            state["section"] = f"Mục {section_match.group(1)}"
            heading = "section"
        elif article_match:
            state["article"] = f"Điều {article_match.group(1)}"
            state["article_title"] = article_match.group(2).strip()
            heading = "article"

        if heading:
            flush()

        if heading and _is_heading_only([paragraph]):
            # A bare "Chương II" / "Mục 1" heading has no answerable content.
            # Keep its state for the next paragraph instead of emitting a chunk,
            # and drop the all-caps title printed below it. Section titles wrap
            # over two lines, so the skip lasts for the whole run of titles.
            skip_titles = heading in {"chapter", "section"}
            continue

        if skip_titles:
            if _is_uppercase_title(paragraph):
                continue
            skip_titles = False

        for piece in _split_long_paragraph(paragraph, max_size):
            addition = len(piece) + (2 if current else 0)
            if current and current_length + addition > max_size:
                flush()
            if not current:
                current_state = dict(state)
            current.append(piece)
            current_length += addition

    flush()

    chunks: list[Chunk] = []
    for index, (group, group_state) in enumerate(groups):
        body = "\n\n".join(group)
        touches_article_heading = any(ARTICLE_HEADING.match(part) for part in group)
        breadcrumb = _breadcrumb(group_state, touches_article_heading) if include_breadcrumb else ""
        text = f"[{breadcrumb}]\n{body}" if breadcrumb else body

        touched = [
            f"Điều {match.group(1)}"
            for match in (ARTICLE_HEADING.match(part) for part in group)
            if match
        ]

        metadata = dict(base)
        metadata.update(
            {
                "chunk_index": index,
                "char_count": len(text),
                "body_char_count": len(body),
                "paragraph_count": len(group),
                "article": group_state.get("article"),
                "chapter": group_state.get("chapter"),
                "section": group_state.get("section"),
                "articles": touched,
                "breadcrumb": breadcrumb,
            }
        )
        chunks.append(
            Chunk(
                chunk_id=_chunk_id(page.document_id, page.page, strategy, index),
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=text,
                metadata=metadata,
            )
        )

    return chunks
