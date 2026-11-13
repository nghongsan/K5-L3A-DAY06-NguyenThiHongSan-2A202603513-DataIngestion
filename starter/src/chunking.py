"""Chunking strategies. Every chunk stays inside one PDF page (page traceability)
and carries document_id / source / page plus chapter and section metadata.

Section of a chunk = the section heading (from the PDF outline) that precedes the
chunk's first character on the page, or the section active at the top of the page.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import Chunk, DocumentPage

# Lines that open a new structural block in OpenStax pages.
_LABEL_LINE = re.compile(
    r"^(CHECKPOINT|CONCEPTS IN PRACTICE|TRY IT|EXPLORING FURTHER|Learning objectives|"
    r"Chapter Outline|Introduction|EXAMPLE \d+\.\d+|[A-Z0-9][A-Z0-9 :,'/()&-]{5,})$")
_SENTENCE_END = re.compile(r"[.:?!\"')]$")
WRAP_WIDTH = 95  # lines shorter than this that end a sentence close a paragraph


def _section_spans(page: DocumentPage) -> list[tuple[int, dict[str, Any]]]:
    """Return [(char_offset, section_meta)] sorted by offset for this page."""
    meta = page.metadata
    spans: list[tuple[int, dict[str, Any]]] = []
    top = ({"section": meta.get("top_section"), "section_title": meta.get("top_section_title")}
           if meta.get("top_section") else {"section": f"{meta.get('chapter')}.0",
                                            "section_title": "Chapter introduction"})
    spans.append((0, top))
    for sec in meta.get("sections_starting", []):
        heading = f"{sec['section']} {sec['section_title']}"
        # last occurrence: the chapter outline on the first page lists headings too
        pos = -1
        for m in re.finditer(r"(?m)^" + re.escape(heading) + r"$", page.text):
            pos = m.start()
        if pos >= 0:
            spans.append((pos, sec))
    spans.sort(key=lambda x: x[0])
    return spans


def _section_at(spans: list[tuple[int, dict[str, Any]]], offset: int) -> dict[str, Any]:
    current = spans[0][1]
    for start, sec in spans:
        if start <= offset:
            current = sec
        else:
            break
    return current


def _make_chunk(page: DocumentPage, strategy: str, index: int, text: str, start: int, end: int,
                spans: list[tuple[int, dict[str, Any]]], params: str) -> Chunk:
    """start/end = exact character span of the chunk inside page.text (end exclusive)."""
    sec = _section_at(spans, start)
    # every section whose text appears in the chunk (a fixed window can cross a heading)
    covered = [sec["section"]] + [s["section"] for off, s in spans if start < off < end
                                  and s["section"] != sec["section"]]
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    # Stable ID: same document/page/strategy params/position -> same ID on re-ingest.
    chunk_id = f"{page.document_id}:{strategy}:{params}:p{page.page:04d}:c{index:02d}"
    return Chunk(
        chunk_id=chunk_id, document_id=page.document_id, source=page.source, page=page.page,
        text=text,
        metadata={
            "chapter": page.metadata.get("chapter"),
            "chapter_title": page.metadata.get("chapter_title"),
            "section": sec["section"],
            "section_title": sec["section_title"],
            "printed_page": page.metadata.get("printed_page") or -1,
            "sections_covered": "|".join(covered),
            "char_start": start,
            "char_end": end,
            "char_len": len(text),
            "content_hash": digest,
            "strategy_params": params,
        },
    )


def fixed_size(page: DocumentPage, size: int, overlap: int, strategy: str = "A") -> list[Chunk]:
    """Split text into fixed character windows with overlap; ignores structure on purpose."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    spans = _section_spans(page)
    params = f"fixed{size}o{overlap}"
    chunks: list[Chunk] = []
    step = size - overlap
    text = page.text
    start = 0
    while start < len(text):
        piece = text[start:start + size]
        if piece.strip():
            lead = len(piece) - len(piece.lstrip())
            body = piece.strip()
            chunks.append(_make_chunk(page, strategy, len(chunks), body, start + lead,
                                      start + lead + len(body), spans, params))
        if start + size >= len(text):
            break
        start += step
    return chunks


def _blocks(text: str) -> list[tuple[int, str]]:
    """Split page text into structural blocks (paragraphs, headed groups).

    Boundaries: section headings / label lines (CHECKPOINT, TRY IT, EXAMPLE ...)
    and paragraph ends (a short line ending a sentence). A short title line that
    precedes a block is kept with that block.
    """
    lines = text.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    cur_start = 0
    prev = ""
    for i, line in enumerate(lines):
        is_heading = bool(re.match(r"^\d{1,2}\.\d{1,2} [A-Z]", line)) or bool(_LABEL_LINE.match(line))
        prev_ends = bool(prev) and len(prev) < WRAP_WIDTH and bool(_SENTENCE_END.search(prev))
        # a bullet list only ends when a non-bullet line follows it
        para_end_before = prev_ends and (not prev.startswith("•") or not line.startswith("•"))
        if current and (is_heading or para_end_before or not line):
            blocks.append((cur_start, current))
            current = []
        if not line:
            prev = line
            continue
        if not current:
            cur_start = offsets[i]
        current.append(line)
        prev = line
    if current:
        blocks.append((cur_start, current))
    return [(start, "\n".join(b)) for start, b in blocks]


def _split_long(text: str, max_size: int) -> list[tuple[int, str]]:
    """Split an oversized block at sentence/line boundaries; offsets are relative."""
    pieces: list[tuple[int, str]] = []
    start = 0
    while len(text) - start > max_size:
        window = text[start:start + max_size]
        cut = max(window.rfind(". "), window.rfind(".\n"), window.rfind("\n"))
        if cut < max_size // 3:
            cut = max_size - 1
        pieces.append((start, text[start:start + cut + 1]))
        start += cut + 1
    pieces.append((start, text[start:]))
    return pieces


def by_paragraph(page: DocumentPage, max_size: int, min_size: int = 200, strategy: str = "B") -> list[Chunk]:
    """Group structural blocks into chunks <= max_size; never cross a section heading.

    Small blocks (titles, short paragraphs) are merged forward until min_size so a
    heading stays with its body; oversized blocks are split at sentence/line ends.
    """
    spans = _section_spans(page)
    section_starts = {s for s, _ in spans[1:]}
    params = f"para{max_size}"
    units: list[tuple[int, str]] = []
    for start, block in _blocks(page.text):
        if len(block) > max_size:
            units.extend((start + rel, piece) for rel, piece in _split_long(block, max_size))
        else:
            units.append((start, block))
    groups: list[tuple[int, int, str]] = []  # (start, end, text)
    cur_start, cur_end, cur_text = None, 0, ""
    for start, unit in units:
        starts_section = start in section_starts
        fits = cur_text and len(cur_text) + 1 + len(unit) <= max_size
        if cur_text and (starts_section or not fits or len(cur_text) >= min_size):
            groups.append((cur_start, cur_end, cur_text))
            cur_start, cur_text = None, ""
        if cur_start is None:
            cur_start, cur_text = start, unit
        else:
            cur_text = cur_text + "\n" + unit
        cur_end = start + len(unit)
    if cur_text:
        # a short page tail is merged backwards instead of becoming a tiny chunk
        if groups and len(cur_text) < min_size and cur_start not in section_starts \
                and len(groups[-1][2]) + 1 + len(cur_text) <= max_size:
            prev_start, _, prev_text = groups.pop()
            groups.append((prev_start, cur_end, prev_text + "\n" + cur_text))
        else:
            groups.append((cur_start, cur_end, cur_text))
    chunks = []
    for start, end, text in groups:
        if not text.strip():
            continue
        lead = len(text) - len(text.lstrip())
        trail = len(text) - len(text.rstrip())
        chunks.append(_make_chunk(page, strategy, len(chunks), text.strip(), start + lead, end - trail,
                                  spans, params))
    return chunks
