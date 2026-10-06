"""Study-mode lesson helpers: title suggestion and table-of-contents extraction.

This module builds on the dependency-free :mod:`pdf_text` reader so uploaded
lesson PDFs can be understood without any third-party packages:

* :func:`analyse_lesson_pdf` returns the page count, a table of contents, and
  a suggested lesson name taken from the document metadata or the first page.
* The table of contents prefers the PDF's own outline (bookmarks) and falls
  back to detecting headings from font sizes when a document has no outline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Any

from pdf_text import PDFDocument, PDFParseError, PageText, Ref, TextRun, extract_pages


class LessonPDFError(Exception):
    """A human-readable lesson PDF failure."""


MAX_TOC_ENTRIES = 300
MAX_HEADING_SCAN_PAGES = 150
MAX_TITLE_LENGTH = 100
MAX_TOC_TITLE_LENGTH = 160

_CHROME_PATTERNS = (
    re.compile(r"^(?:https?://|www\.)\S*$", re.IGNORECASE),
    re.compile(r"^(?:page\s+)?\d+\s*(?:/|of)\s*\d+$", re.IGNORECASE),
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}"),
)

_GENERIC_TITLE_WORDS = {
    "untitled",
    "untitled document",
    "microsoft word",
    "word document",
    "pdf document",
    "document",
}


@dataclass
class _Line:
    y: float
    x0: float
    x1: float
    text: str
    size: float
    bold: bool


def _clean(text: str) -> str:
    text = (
        text.replace("­", "")
        .replace("ﬁ", "fi")
        .replace("ﬂ", "fl")
        .replace(" ", " ")
    )
    return " ".join(text.split())


def decode_pdf_string(value: Any) -> str:
    """Decode a PDF literal/hex string (bytes) or name into readable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return _clean(value)
    if not isinstance(value, (bytes, bytearray)):
        return ""
    raw = bytes(value)
    if raw.startswith(b"\xfe\xff"):
        try:
            return _clean(raw[2:].decode("utf-16-be", errors="replace"))
        except Exception:
            return ""
    if raw.startswith(b"\xff\xfe"):
        try:
            return _clean(raw[2:].decode("utf-16-le", errors="replace"))
        except Exception:
            return ""
    # PDFDocEncoding matches latin-1 for the printable Western range, which is
    # close enough for outline/bookmark titles.
    return _clean(raw.decode("latin-1", errors="replace"))


def _is_chrome(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if lowered in _GENERIC_TITLE_WORDS:
        return True
    return any(pattern.match(stripped) for pattern in _CHROME_PATTERNS)


def _catalog(doc: PDFDocument) -> dict[str, Any] | None:
    root = doc.resolve(doc.trailer.get("Root"))
    if isinstance(root, dict):
        return root
    return None


def page_refs_in_order(doc: PDFDocument) -> list[int]:
    """Return the page object numbers in document order for dest resolution."""
    refs: list[int] = []
    seen: set[int] = set()
    catalog = _catalog(doc)

    def walk(node_ref: Any, depth: int) -> None:
        if depth > 64:
            return
        if isinstance(node_ref, Ref):
            if node_ref.num in seen:
                return
            seen.add(node_ref.num)
        node = doc.resolve(node_ref)
        if not isinstance(node, dict):
            return
        node_type = node.get("Type")
        kids = doc.resolve(node.get("Kids"))
        if node_type == "Page" or (node_type != "Pages" and kids is None and "Contents" in node):
            if isinstance(node_ref, Ref):
                refs.append(node_ref.num)
            return
        if isinstance(kids, list):
            for kid in kids:
                walk(kid, depth + 1)

    if catalog is not None:
        walk(catalog.get("Pages"), 0)
    if not refs:
        for num in sorted(doc._all_object_numbers()):
            obj = doc.resolve(doc.get_object(num))
            if isinstance(obj, dict) and obj.get("Type") == "Page":
                refs.append(num)
    return refs


def _name_tree_lookup(doc: PDFDocument, node: Any, wanted: str, depth: int = 0) -> Any:
    """Look up a key in a PDF name tree (used for named destinations)."""
    if depth > 16:
        return None
    node = doc.resolve(node)
    if not isinstance(node, dict):
        return None
    names = doc.resolve(node.get("Names"))
    if isinstance(names, list):
        for index in range(0, len(names) - 1, 2):
            key = decode_pdf_string(names[index])
            if key == wanted:
                return doc.resolve(names[index + 1])
    kids = doc.resolve(node.get("Kids"))
    if isinstance(kids, list):
        for kid in kids:
            found = _name_tree_lookup(doc, kid, wanted, depth + 1)
            if found is not None:
                return found
    return None


def _named_dest(doc: PDFDocument, name: str) -> Any:
    catalog = _catalog(doc)
    if catalog is None:
        return None
    names = doc.resolve(catalog.get("Names"))
    if isinstance(names, dict):
        dests_tree = doc.resolve(names.get("Dests"))
        found = _name_tree_lookup(doc, dests_tree, name)
        if found is not None:
            return found
    dests = doc.resolve(catalog.get("Dests"))
    if isinstance(dests, dict):
        for key, value in dests.items():
            if str(key) == name:
                return doc.resolve(value)
    return None


def _dest_to_page(doc: PDFDocument, dest: Any, page_index: dict[int, int], page_count: int) -> int | None:
    """Resolve an outline destination to a 1-based page number (or None)."""
    dest = doc.resolve(dest)
    if isinstance(dest, (bytes, bytearray)):
        return _dest_to_page(doc, decode_pdf_string(dest), page_index, page_count)
    if isinstance(dest, str):
        if not dest:
            return None
        return _dest_to_page(doc, _named_dest(doc, dest), page_index, page_count)
    if isinstance(dest, dict):
        # A GoTo action dictionary: /D holds the real destination.
        action = doc.resolve(dest.get("D"))
        if action is None:
            return None
        return _dest_to_page(doc, action, page_index, page_count)
    if isinstance(dest, list) and dest:
        raw_first = dest[0]
        if isinstance(raw_first, Ref):
            position = page_index.get(raw_first.num)
            return position + 1 if position is not None else None
        first = doc.resolve(raw_first)
        if isinstance(first, int) and not isinstance(first, bool):
            # Some writers store a zero-based page number instead of a page ref.
            if 0 <= first < page_count:
                return first + 1
        return None
    return None


def _outline_action_dest(doc: PDFDocument, item: dict[str, Any]) -> Any:
    action = doc.resolve(item.get("A"))
    if isinstance(action, dict):
        return doc.resolve(action.get("D"))
    if isinstance(action, list):
        for entry in action:
            resolved = doc.resolve(entry)
            if isinstance(resolved, dict) and resolved.get("D") is not None:
                return doc.resolve(resolved.get("D"))
    return None


def extract_outline(doc: PDFDocument) -> list[dict[str, Any]]:
    """Read the PDF bookmark outline as [{title, page, level}]."""
    catalog = _catalog(doc)
    if catalog is None:
        return []
    outlines = doc.resolve(catalog.get("Outlines"))
    if not isinstance(outlines, dict):
        return []
    page_refs = page_refs_in_order(doc)
    page_index = {num: position for position, num in enumerate(page_refs)}
    page_count = len(page_refs)
    entries: list[dict[str, Any]] = []
    visited: set[int] = set()

    def walk(item_ref: Any, level: int, depth: int) -> None:
        if depth > 64 or len(entries) >= MAX_TOC_ENTRIES:
            return
        if isinstance(item_ref, Ref):
            if item_ref.num in visited:
                return
            visited.add(item_ref.num)
        item = doc.resolve(item_ref)
        if not isinstance(item, dict):
            return
        title = decode_pdf_string(item.get("Title"))[:MAX_TOC_TITLE_LENGTH].strip()
        if title:
            dest = doc.resolve(item.get("Dest"))
            if dest is None:
                dest = _outline_action_dest(doc, item)
            page = _dest_to_page(doc, dest, page_index, page_count)
            if page is not None:
                entries.append({"title": title, "page": page, "level": min(level, 5)})
        first = item.get("First")
        if first is not None:
            walk(first, level + 1, depth + 1)
        sibling = item.get("Next")
        if sibling is not None:
            walk(sibling, level, depth + 1)

    first_item = outlines.get("First")
    if first_item is not None:
        walk(first_item, 0, 0)
    return entries


def _group_lines(runs: list[TextRun]) -> list[_Line]:
    ordered = sorted((run for run in runs if run.text and run.text.strip()), key=lambda r: (-round(r.y * 2) / 2, r.x0))
    lines: list[_Line] = []
    for run in ordered:
        text = _clean(run.text)
        if not text:
            continue
        tolerance = max(1.5, run.size * 0.35)
        target: _Line | None = None
        for line in reversed(lines[-8:]):
            if abs(line.y - run.y) <= tolerance:
                target = line
                break
        bold = "bold" in (run.font or "").lower()
        if target is None:
            lines.append(_Line(run.y, run.x0, run.x1, text, run.size, bold))
            continue
        gap = run.x0 - target.x1
        if gap > max(0.9, target.size * 0.15) and target.text and not target.text.endswith(" ") and not text.startswith(" "):
            target.text += " "
        elif gap < -max(1.0, target.size * 0.5):
            target.text += " "
        target.text += text
        target.x0 = min(target.x0, run.x0)
        target.x1 = max(target.x1, run.x1)
        target.size = max(target.size, run.size)
        target.bold = target.bold or bold
    cleaned: list[_Line] = []
    for line in lines:
        line.text = _clean(line.text)
        if line.text:
            cleaned.append(line)
    return cleaned


def _heading_candidates(pages: list[PageText]) -> tuple[list[tuple[int, _Line]], float]:
    per_page: list[tuple[int, _Line]] = []
    body_sizes: list[float] = []
    for page_number, page in enumerate(pages, start=1):
        lines = _group_lines(page.runs)
        for line in lines:
            if len(line.text) >= 25 and not _is_chrome(line.text):
                body_sizes.append(line.size)
            per_page.append((page_number, line))
    typical = float(median(body_sizes)) if body_sizes else 0.0
    if not typical:
        sizes = sorted(line.size for _, line in per_page)
        typical = float(sizes[len(sizes) // 2]) if sizes else 11.0
    return per_page, typical


def build_heading_toc(pages: list[PageText]) -> list[dict[str, Any]]:
    """Detect headings from font sizes when a PDF has no bookmark outline."""
    per_page, typical = _heading_candidates(pages)
    if typical <= 0:
        return []
    strong_threshold = max(typical * 1.55, typical + 3.0)
    heading_threshold = max(typical * 1.28, typical + 1.5)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for page_number, line in per_page:
        text = line.text
        if _is_chrome(text):
            continue
        if not (3 <= len(text) <= MAX_TOC_TITLE_LENGTH):
            continue
        if not re.search(r"[A-Za-z]", text):
            continue
        words = len(text.split())
        if words > 22 or words < 1:
            continue
        is_strong = line.size >= strong_threshold
        is_heading = line.size >= heading_threshold or (line.bold and line.size >= typical + 0.5 and words <= 12)
        if not is_heading:
            continue
        # Skip lines that look like wrapped body sentences rather than titles.
        if words > 12 and text.endswith((".", ":", ";")):
            continue
        key = (text.casefold(), page_number)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"title": text, "page": page_number, "level": 0 if is_strong else 1})
        if len(entries) >= MAX_TOC_ENTRIES:
            break
    # A credible heading TOC needs entries beyond the first pages; a handful of
    # false positives is worse than no TOC at all.
    if len(entries) < 2:
        return []
    return entries


def document_info_title(doc: PDFDocument) -> str:
    info = doc.resolve(doc.trailer.get("Info"))
    if not isinstance(info, dict):
        return ""
    return decode_pdf_string(info.get("Title"))


def suggest_title(doc: PDFDocument, first_page: PageText | None, filename: str) -> tuple[str, str]:
    """Suggest a lesson name: metadata title, first-page heading, or filename."""
    metadata = document_info_title(doc)
    if metadata and not _is_chrome(metadata) and re.search(r"[A-Za-z0-9]", metadata):
        return metadata[:MAX_TITLE_LENGTH].strip(), "pdf"
    if first_page is not None:
        lines = [line for line in _group_lines(first_page.runs) if not _is_chrome(line.text)]
        lettered = [line for line in lines if re.search(r"[A-Za-z]", line.text) and 2 <= len(line.text) <= 160]
        if lettered:
            lettered.sort(key=lambda line: (round(line.size * 2), line.y), reverse=True)
            top = lettered[0]
            title = top.text
            # Titles sometimes wrap over two adjacent same-size lines.
            if len(title) <= 60:
                for other in lettered[1:6]:
                    if abs(other.size - top.size) <= 0.6 and len(other.text) <= 60:
                        if 0 < abs(other.y - top.y) <= max(8.0, top.size * 2.5):
                            first, second = (top, other) if top.y >= other.y else (other, top)
                            title = f"{first.text} — {second.text}"
                            break
            if title and re.search(r"[A-Za-z0-9]", title):
                return title[:MAX_TITLE_LENGTH].strip(), "first_page"
    stem = re.sub(r"\.pdf$", "", (filename or "").strip(), flags=re.IGNORECASE)
    stem = _clean(re.sub(r"[_\-]+", " ", stem))
    if stem and re.search(r"[A-Za-z0-9]", stem):
        return stem[:MAX_TITLE_LENGTH].strip(), "filename"
    return "Untitled lesson", "filename"


def first_page_excerpt(first_page: PageText | None, limit: int = 400) -> str:
    if first_page is None:
        return ""
    lines = _group_lines(first_page.runs)
    lines.sort(key=lambda line: (-line.y, line.x0))
    text = _clean(" ".join(line.text for line in lines))
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def analyse_lesson_pdf(data: bytes, filename: str) -> dict[str, Any]:
    """Parse a lesson PDF into page count, TOC, and a suggested lesson name."""
    try:
        doc = PDFDocument(data)
    except PDFParseError as error:
        raise LessonPDFError(str(error) or "That file could not be read as a PDF.") from error
    page_count = len(page_refs_in_order(doc))
    if page_count < 1:
        raise LessonPDFError("The PDF does not contain any readable pages.")
    if page_count > 2000:
        raise LessonPDFError("That PDF has more than 2,000 pages; split it into smaller lessons.")

    toc = extract_outline(doc)
    toc_source = "outline" if toc else "none"

    scan_pages = min(page_count, MAX_HEADING_SCAN_PAGES)
    first_page: PageText | None = None
    heading_pages: list[PageText] = []
    try:
        heading_pages = extract_pages(data, max_pages=scan_pages)
    except PDFParseError:
        heading_pages = []
    if heading_pages:
        first_page = heading_pages[0]
    if not toc and heading_pages:
        toc = build_heading_toc(heading_pages)
        if toc:
            toc_source = "headings"

    suggested_title, title_source = suggest_title(doc, first_page, filename)
    return {
        "page_count": page_count,
        "toc": toc,
        "toc_source": toc_source,
        "toc_partial": toc_source == "headings" and page_count > scan_pages,
        "suggested_title": suggested_title,
        "title_source": title_source,
        "excerpt": first_page_excerpt(first_page),
    }


def normalise_stored_toc(value: Any) -> list[dict[str, Any]]:
    """Tolerantly validate a stored/imported table of contents."""
    if not isinstance(value, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in value[:MAX_TOC_ENTRIES]:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        page = item.get("page")
        level = item.get("level", 0)
        if not isinstance(title, str):
            continue
        title = _clean(title)[:MAX_TOC_TITLE_LENGTH]
        if not title or not isinstance(page, int) or isinstance(page, bool):
            continue
        if page < 1 or page > 2000:
            continue
        if not isinstance(level, int) or isinstance(level, bool):
            level = 0
        entries.append({"title": title, "page": page, "level": max(0, min(level, 5))})
    return entries
