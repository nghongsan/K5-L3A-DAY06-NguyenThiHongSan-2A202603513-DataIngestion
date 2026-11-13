"""Read and normalize the PDF corpus while keeping page-level traceability.

Every returned DocumentPage keeps the *physical* PDF page number (1-based), the
printed page number found in the footer, and chapter/section metadata derived
from the PDF outline (bookmarks) — never guessed from content.
"""
from __future__ import annotations

import json
import re
import unicodedata
from bisect import bisect_right
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .models import DocumentPage

# Footer / boilerplate lines produced by every OpenStax page.
_FOOTER_PATTERNS = [
    re.compile(r"^Access for free at openstax\.org\s*$"),
    # even page footer: "90     4 • Decisions"
    re.compile(r"^(\d{1,4})\s+\d{1,2}\s+•\s+.+$"),
    # odd page footer: "6.2 • Control flow     141"
    re.compile(r"^\d{1,2}\.\d{1,2}\s+•\s+.+?\s{2,}(\d{1,4})\s*$"),
    # chapter summary pages: "4 • Chapter summary   113" handled by the two above
]
_MULTIMEDIA = re.compile(r"Access multimedia content \(http[^)]*\)", re.S)
_SECTION_TITLE = re.compile(r"^(\d{1,2})\.(\d{1,2}) (.+)$")
_CHAPTER_TITLE = re.compile(r"^Chapter (\d{1,2}) (.+)$")


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFKC) and whitespace while keeping line structure.

    - NFKC folds ligatures (ﬁ -> fi) and full-width forms; curly quotes are mapped
      to ASCII so that evidence matching is robust.
    - Trailing spaces are stripped per line, runs of spaces collapsed, and runs of
      blank lines collapsed to a single blank line. Newlines are kept because
      the paragraph chunker uses them.
    """
    text = unicodedata.normalize("NFKC", text)
    text = (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "-")
                .replace(" ", " ").replace("​", ""))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _strip_boilerplate(raw: str) -> tuple[str, int | None]:
    """Remove page footers / multimedia links; return text and printed page no."""
    printed: int | None = None
    kept: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        matched = False
        for pat in _FOOTER_PATTERNS:
            m = pat.match(stripped)
            if m:
                matched = True
                if m.groups() and m.group(1):
                    printed = int(m.group(1))
                break
        if not matched:
            kept.append(line)
    # "TRY IT" sidebar labels are extracted out of reading order -> drop them.
    kept = [line for line in kept if line.strip() != "TRY IT"]
    # First page of a chapter ends with the decorative "<Chapter title>\n<number>".
    if len(kept) >= 2 and re.fullmatch(r"\d{1,2}", kept[-1].strip()) and re.fullmatch(r"[A-Z][a-z]+", kept[-2].strip()):
        kept = kept[:-2]
    text = "\n".join(kept)
    text = _MULTIMEDIA.sub("", text)
    return text, printed


def _outline_entries(reader: PdfReader) -> list[dict[str, Any]]:
    """Flatten chapter (depth 0) and section (depth 1) bookmarks with start pages."""
    entries: list[dict[str, Any]] = []

    def walk(items: list, depth: int, chapter: dict | None) -> None:
        current = chapter
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1, current)
                continue
            title = item.title.strip()
            page = reader.get_destination_page_number(item) + 1
            if depth == 0:
                m = _CHAPTER_TITLE.match(title)
                current = ({"chapter": int(m.group(1)), "chapter_title": m.group(2), "page": page}
                           if m else None)
                if current:
                    entries.append({**current, "kind": "chapter"})
            elif depth == 1 and current:
                m = _SECTION_TITLE.match(title)
                if m and int(m.group(1)) == current["chapter"]:
                    entries.append({"kind": "section", "chapter": current["chapter"],
                                    "chapter_title": current["chapter_title"],
                                    "section": f"{m.group(1)}.{m.group(2)}",
                                    "section_title": m.group(3).strip(), "page": page})

    walk(reader.outline, 0, None)
    return entries


def load_pdf(path: Path, document_id: str, source: str, page_range: tuple[int, int] | None = None,
             min_chars: int = 200, log: list[dict[str, Any]] | None = None) -> list[DocumentPage]:
    """Extract each physical page; keep its page number, source and outline metadata.

    Pages whose normalized text is shorter than ``min_chars`` are logged as empty
    and excluded. Extraction errors are logged, never silently dropped.
    """
    reader = PdfReader(str(path))
    outline = _outline_entries(reader)
    sections = [e for e in outline if e["kind"] == "section"]
    section_starts = [s["page"] for s in sections]
    log = log if log is not None else []
    first, last = page_range or (1, len(reader.pages))
    pages: list[DocumentPage] = []
    for number in range(first, last + 1):
        try:
            raw = reader.pages[number - 1].extract_text() or ""
        except Exception as exc:  # noqa: BLE001 — log every extraction failure
            log.append({"page": number, "status": "error", "detail": repr(exc)})
            continue
        body, printed = _strip_boilerplate(raw)
        text = normalize_text(body)
        if len(text) < min_chars:
            log.append({"page": number, "status": "empty_or_short", "chars": len(text),
                        "detail": "only footer/figure text after cleaning"})
            continue
        # Sections that started on or before this page (outline is authoritative).
        idx = bisect_right(section_starts, number) - 1
        sec_on_entry = sections[idx] if idx >= 0 else None
        starting_here = [s for s in sections if s["page"] == number]
        chapter_meta = sec_on_entry or (starting_here[0] if starting_here else None)
        # Section active at the top of the page = last section that started on an
        # earlier page; sections starting here are located by heading in chunking.
        prev = [s for s in sections if s["page"] < number]
        top_section = prev[-1] if prev and chapter_meta and prev[-1]["chapter"] == chapter_meta["chapter"] else None
        metadata = {
            "printed_page": printed,
            "chapter": chapter_meta["chapter"] if chapter_meta else None,
            "chapter_title": chapter_meta["chapter_title"] if chapter_meta else None,
            "top_section": top_section["section"] if top_section else None,
            "top_section_title": top_section["section_title"] if top_section else None,
            "sections_starting": [{"section": s["section"], "section_title": s["section_title"]}
                                  for s in starting_here],
            "chars": len(text),
        }
        pages.append(DocumentPage(document_id=document_id, source=source, page=number,
                                  text=text, metadata=metadata))
        log.append({"page": number, "status": "ok", "chars": len(text), "printed_page": printed})
    return pages


def save_pages(pages: list[DocumentPage], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for p in pages:
            fh.write(json.dumps({"document_id": p.document_id, "source": p.source, "page": p.page,
                                 "text": p.text, "metadata": p.metadata}, ensure_ascii=False) + "\n")
