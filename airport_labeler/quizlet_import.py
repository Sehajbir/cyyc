"""Turn a PDF saved from a Quizlet print page into (term, definition) pairs.

Quizlet's print view (``https://quizlet.com/<set-id>/print``) renders the set as a
table with the term on the left and the definition on the right. When a browser
saves that page as a PDF, each table row becomes a group of text lines whose
left cell text sits left of a column boundary and whose right cell text sits to
the right of it. Long cells wrap over several baselines, and rows can continue
across page breaks.

The importer works purely on geometry so it does not depend on the exact
HTML/CSS Quizlet ships:

1. Extract positioned text runs and table borders using :mod:`pdf_text`.
2. Find the column split (a vertical border if present, otherwise the widest
   gap in the horizontal distribution of text across the page).
3. Group runs into visual lines by baseline, then split each line into left and
   right cells.
4. Delimit rows using horizontal borders when present, otherwise using a new
   left-cell line following a non-empty right cell.
5. Drop print chrome (page headers/footers, browser-added URL/date lines, the
   "Terms / Definitions" header row, page numbers).

It only depends on the standard library so it can run inside the existing
dependency-free deployment image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from pdf_text import PDFParseError, PageText, TextRun, extract_pages

MAX_CARD_TEXT = 2_000
MAX_CARDS = 1_000

QUIZLET_URL_RE = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)*quizlet\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:(?:[a-z0-9-]+/)?(\d{5,}))(?:/[^?#]*)?(?:[?#].*)?$",
    re.IGNORECASE,
)

# Lines browsers add to printed pages plus Quizlet's own print chrome.
_CHROME_PATTERNS = [
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?", re.IGNORECASE),  # Chrome date header
    re.compile(r"^(?:https?://)?(?:www\.)?quizlet\.com/\S*", re.IGNORECASE),  # URL footer
    re.compile(r"^(?:page\s+)?\d+\s*(?:/|of)\s*\d+$", re.IGNORECASE),  # page x of y
    re.compile(r"^\d{1,3}$"),  # bare page number
    re.compile(r"^(?:study online at|print(?:ed)? (?:from|on|with) quizlet|quizlet(?: inc\.?)?)\b.*", re.IGNORECASE),
    re.compile(r"^(?:terms?|definitions?)\s*(?:[\(\[]\s*\d+\s*[\)\]])?\s*$", re.IGNORECASE),
    re.compile(r"^\d+\s+terms?(?:\s+in\s+this\s+set)?(?:\s*\(\d+\))?$", re.IGNORECASE),
    re.compile(r"^terms in this set\s*\(\d+\)$", re.IGNORECASE),
    re.compile(r"^(?:created by|last updated|by)\b.*", re.IGNORECASE),
]
_HEADER_ROW_RE = re.compile(r"^(?:terms?|words?|questions?|fronts?)$", re.IGNORECASE)
_HEADER_ROW_RIGHT_RE = re.compile(r"^(?:definitions?|meanings?|answers?|backs?)$", re.IGNORECASE)
_LEADING_NUMBER_RE = re.compile(r"^\(?\d{1,4}[\.\)]\s+")


class QuizletImportError(Exception):
    """Human-readable import failure."""


def normalise_quizlet_url(value: object) -> str:
    """Validate and canonicalise a Quizlet set / print URL."""
    if not isinstance(value, str):
        raise QuizletImportError("Enter the Quizlet print URL for the set.")
    text = value.strip()
    if not text:
        raise QuizletImportError("Enter the Quizlet print URL for the set.")
    if len(text) > 500:
        raise QuizletImportError("That URL is too long to be a Quizlet set link.")
    match = QUIZLET_URL_RE.match(text)
    if not match:
        raise QuizletImportError(
            "That does not look like a Quizlet set link. Use the print page address, for example https://quizlet.com/123456789/print."
        )
    set_id = match.group(1)
    return f"https://quizlet.com/{set_id}/print"


@dataclass
class Card:
    term: str
    definition: str


@dataclass
class _Line:
    y: float
    x0: float
    x1: float
    text: str
    size: float
    page: int


@dataclass
class _Row:
    left: list[str] = field(default_factory=list)
    right: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(part.strip() for part in self.left) and not any(part.strip() for part in self.right)


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = text.replace("\u00a0", " ")
    return " ".join(text.split())


def _is_chrome(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return any(pattern.match(stripped) for pattern in _CHROME_PATTERNS)


def _group_lines(runs: Iterable[TextRun], page_index: int) -> list[_Line]:
    """Merge text runs that share a baseline into visual lines."""
    ordered = sorted((r for r in runs if r.text), key=lambda r: (-round(r.y * 2) / 2, r.x0))
    lines: list[_Line] = []
    for run in ordered:
        tolerance = max(1.5, run.size * 0.35)
        target = None
        for line in reversed(lines[-6:]):
            if abs(line.y - run.y) <= tolerance:
                target = line
                break
        if target is None:
            lines.append(_Line(run.y, run.x0, run.x1, run.text, run.size, page_index))
            continue
        gap = run.x0 - target.x1
        if gap > max(0.9, target.size * 0.15) and target.text and not target.text.endswith(" ") and not run.text.startswith(" "):
            target.text += " "
        elif gap < -max(1.0, target.size * 0.5):
            # Run drawn left of the current line end (e.g. a second column
            # emitted after the first). Keep reading order by x instead.
            target.text += " "
        target.text += run.text
        target.x0 = min(target.x0, run.x0)
        target.x1 = max(target.x1, run.x1)
        target.size = max(target.size, run.size)
    for line in lines:
        line.text = _clean(line.text)
    return [line for line in lines if line.text]


def _split_line_by_gap(line_runs: list[TextRun], split_x: float) -> tuple[str, str]:
    left = [r for r in line_runs if (r.x0 + r.x1) / 2 < split_x]
    right = [r for r in line_runs if (r.x0 + r.x1) / 2 >= split_x]
    return (
        _clean("".join(_join_runs(left))),
        _clean("".join(_join_runs(right))),
    )


def _join_runs(runs: list[TextRun]) -> list[str]:
    parts: list[str] = []
    previous: TextRun | None = None
    for run in sorted(runs, key=lambda r: r.x0):
        if previous is not None:
            gap = run.x0 - previous.x1
            if gap > max(0.9, previous.size * 0.15) and parts and not parts[-1].endswith(" ") and not run.text.startswith(" "):
                parts.append(" ")
        parts.append(run.text)
        previous = run
    return parts


def _column_split(page: PageText, body_runs: list[TextRun]) -> float | None:
    """Find the x position dividing the term column from the definition column."""
    if not body_runs:
        return None
    # 1. Explicit vertical borders that span a good part of the page.
    candidates = []
    for rule in page.rules:
        if rule.orientation != "v":
            continue
        span = rule.end - rule.start
        if span < page.height * 0.08:
            continue
        if rule.position <= page.width * 0.12 or rule.position >= page.width * 0.88:
            continue
        candidates.append((span, rule.position))
    if candidates:
        # Cluster positions and pick the one with the most text on both sides.
        positions = sorted(pos for _, pos in candidates)
        clusters: list[list[float]] = []
        for pos in positions:
            if clusters and pos - clusters[-1][-1] <= 3.0:
                clusters[-1].append(pos)
            else:
                clusters.append([pos])
        best = None
        for cluster in clusters:
            x = sum(cluster) / len(cluster)
            left = sum(1 for r in body_runs if r.x1 <= x + 1)
            right = sum(1 for r in body_runs if r.x0 >= x - 1)
            crossing = sum(1 for r in body_runs if r.x0 < x - 1 < r.x1 - 1)
            score = min(left, right) - crossing * 3
            if left and right and (best is None or score > best[0]):
                best = (score, x)
        if best is not None and best[0] > 0:
            return best[1]

    # 2. Gap analysis: find the widest vertical band with no text.
    xs = sorted((r.x0, r.x1) for r in body_runs)
    min_x = min(x0 for x0, _ in xs)
    max_x = max(x1 for _, x1 in xs)
    if max_x - min_x < 60:
        return None
    # Only consider splits within the middle of the text extent.
    lo = min_x + (max_x - min_x) * 0.12
    hi = min_x + (max_x - min_x) * 0.75
    resolution = 2.0
    buckets = int((max_x - min_x) / resolution) + 2
    occupancy = [0] * buckets
    for x0, x1 in xs:
        start = max(0, int((x0 - min_x) / resolution))
        end = min(buckets - 1, int((x1 - min_x) / resolution))
        for i in range(start, end + 1):
            occupancy[i] += 1
    best_gap = None
    i = 0
    while i < buckets:
        if occupancy[i] == 0:
            j = i
            while j < buckets and occupancy[j] == 0:
                j += 1
            gap_start = min_x + i * resolution
            gap_end = min_x + j * resolution
            centre = (gap_start + gap_end) / 2
            if lo <= centre <= hi:
                width = gap_end - gap_start
                if best_gap is None or width > best_gap[0]:
                    best_gap = (width, gap_start, gap_end)
            i = j
        else:
            i += 1
    if best_gap is None or best_gap[0] < 6:
        # No clean gap; use the most common left edge of "second" runs on a line.
        starts: dict[int, int] = {}
        by_line: dict[int, list[TextRun]] = {}
        for run in body_runs:
            by_line.setdefault(round(run.y), []).append(run)
        for runs in by_line.values():
            runs.sort(key=lambda r: r.x0)
            for prev, nxt in zip(runs, runs[1:]):
                if nxt.x0 - prev.x1 > prev.size * 1.5:
                    key = round(nxt.x0 / 4) * 4
                    starts[key] = starts.get(key, 0) + 1
        if not starts:
            return None
        common = max(starts.items(), key=lambda item: item[1])
        if common[1] < 2:
            return None
        return common[0] - 2.0
    # Prefer the left edge of the right column (text starts there) minus a hair.
    return best_gap[2] - 1.0


def _row_boundaries(page: PageText, split_x: float) -> list[float]:
    """Y positions of horizontal borders that cross the column split."""
    ys: list[float] = []
    for rule in page.rules:
        if rule.orientation != "h":
            continue
        if rule.end - rule.start < page.width * 0.25:
            continue
        if not (rule.start - 6 <= split_x <= rule.end + 6):
            continue
        ys.append(rule.position)
    ys.sort(reverse=True)
    merged: list[float] = []
    for y in ys:
        if merged and abs(merged[-1] - y) <= 2.5:
            continue
        merged.append(y)
    return merged


def _page_rows(page: PageText, page_index: int) -> tuple[list[_Row], bool]:
    """Return rows for a page and whether the last row was closed by a border."""
    lines_runs: dict[int, list[TextRun]] = {}
    for run in page.runs:
        if not run.text.strip():
            continue
        key = None
        for existing in lines_runs:
            if abs(existing - run.y) <= max(1.5, run.size * 0.35):
                key = existing
                break
        if key is None:
            key = run.y
            lines_runs[key] = []
        lines_runs[key].append(run)

    # Remove chrome lines (header/footer) before analysing columns.
    body: dict[float, list[TextRun]] = {}
    for y, runs in lines_runs.items():
        text = _clean("".join(_join_runs(runs)))
        if _is_chrome(text):
            continue
        # Browser headers/footers sit within ~4% of the page edge.
        if y > page.height * 0.965 or y < page.height * 0.03:
            continue
        body[y] = runs
    body_runs = [r for runs in body.values() for r in runs]
    if not body_runs:
        return [], True
    split_x = _column_split(page, body_runs)
    if split_x is None:
        # Single-column output (e.g. glossary layout) — fall back to line pairs.
        rows: list[_Row] = []
        for y in sorted(body, reverse=True):
            text = _clean("".join(_join_runs(body[y])))
            rows.append(_Row(left=[text]))
        return rows, True

    borders = _row_boundaries(page, split_x)
    ordered_ys = sorted(body, reverse=True)
    rows = []
    current = _Row()
    last_border_index = -1
    closed_by_border = False

    def border_index_for(y: float) -> int:
        # Number of borders above this y (borders sorted top→bottom).
        count = 0
        for by in borders:
            if by > y + 0.5:
                count += 1
        return count

    # Borderless tables: wrapped lines inside one cell sit one line-height
    # apart, while consecutive rows are separated by cell padding as well, so
    # a gap clearly larger than the font's line height starts a new row.
    prev_y: float | None = None
    for y in ordered_ys:
        left_text, right_text = _split_line_by_gap(body[y], split_x)
        if _HEADER_ROW_RE.match(left_text) and (_HEADER_ROW_RIGHT_RE.match(right_text) or not right_text):
            prev_y = y
            continue
        if borders:
            idx = border_index_for(y)
            if idx != last_border_index and last_border_index != -1 and not current.is_empty():
                rows.append(current)
                current = _Row()
            last_border_index = idx
        else:
            gap = (prev_y - y) if prev_y is not None else 0.0
            line_size = max((r.size for r in body[y]), default=10.0) or 10.0
            wide_gap = gap > line_size * 1.75
            # Fall back to "left text after a completed pair" only when the
            # first line of a page (no measurable gap) starts with a term.
            starts_new = bool(left_text) and (wide_gap or (prev_y is None and bool(current.left and current.right)))
            if starts_new and not current.is_empty():
                rows.append(current)
                current = _Row()
        if left_text:
            current.left.append(left_text)
        if right_text:
            current.right.append(right_text)
        prev_y = y
    if not current.is_empty():
        rows.append(current)
        if borders:
            # A border after the last text line means the row is complete.
            lowest_text = min(ordered_ys) if ordered_ys else 0
            closed_by_border = any(by < lowest_text - 0.5 for by in borders)
    else:
        closed_by_border = True
    return rows, closed_by_border


def _merge_rows(pages_rows: list[tuple[list[_Row], bool]]) -> list[_Row]:
    merged: list[_Row] = []
    carry_open = False
    for rows, closed in pages_rows:
        if not rows:
            continue
        if carry_open and merged and rows:
            first = rows[0]
            previous = merged[-1]
            # Continue the previous row only if the page starts with a
            # definition-only fragment (no new term on the left).
            if not first.left and first.right:
                previous.right.extend(first.right)
                rows = rows[1:]
        merged.extend(rows)
        carry_open = not closed
    return merged


def _row_to_card(row: _Row) -> Card | None:
    term = _clean(" ".join(row.left))
    definition = _clean(" ".join(row.right))
    term = _LEADING_NUMBER_RE.sub("", term)
    if not term and not definition:
        return None
    if _is_chrome(term) and not definition:
        return None
    if _HEADER_ROW_RE.match(term) and (_HEADER_ROW_RIGHT_RE.match(definition) or not definition):
        return None
    if not term or not definition:
        return None
    return Card(term[:MAX_CARD_TEXT], definition[:MAX_CARD_TEXT])


def _pair_single_column(rows: list[_Row]) -> list[Card]:
    """Glossary layouts print term and definition on alternating lines."""
    texts = [_clean(" ".join(row.left + row.right)) for row in rows]
    texts = [t for t in texts if t and not _is_chrome(t)]
    cards: list[Card] = []
    for index in range(0, len(texts) - 1, 2):
        cards.append(Card(texts[index][:MAX_CARD_TEXT], texts[index + 1][:MAX_CARD_TEXT]))
    return cards


def parse_quizlet_pdf(data: bytes) -> list[Card]:
    """Parse a Quizlet print PDF into cards. Raises QuizletImportError."""
    if not data:
        raise QuizletImportError("The uploaded file is empty.")
    try:
        pages = extract_pages(data)
    except PDFParseError as error:
        raise QuizletImportError(str(error)) from error
    except (RecursionError, MemoryError) as error:
        raise QuizletImportError("The PDF is too complex to read.") from error
    if not any(page.runs for page in pages):
        raise QuizletImportError(
            "No text could be read from the PDF. Make sure it was saved from Quizlet's print page rather than scanned or exported as images."
        )
    pages_rows = [_page_rows(page, index) for index, page in enumerate(pages)]
    rows = _merge_rows(pages_rows)
    cards: list[Card] = []
    two_column = any(row.left and row.right for row in rows)
    if two_column:
        for row in rows:
            card = _row_to_card(row)
            if card:
                cards.append(card)
    else:
        cards = _pair_single_column(rows)
    # Remove exact duplicates while preserving order.
    seen: set[tuple[str, str]] = set()
    unique: list[Card] = []
    for card in cards:
        key = (card.term.casefold(), card.definition.casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(card)
    if not unique:
        raise QuizletImportError(
            "No term/definition pairs were found. Open the Quizlet print page, choose the Table or Glossary layout, then save it as a PDF and try again."
        )
    if len(unique) > MAX_CARDS:
        raise QuizletImportError(f"The PDF contains more than {MAX_CARDS} cards. Split the Quizlet set before importing.")
    return unique


def parse_quizlet_export_text(text: str) -> list[Card]:
    """Parse Quizlet's plain-text export (tab or ' - ' separated lines)."""
    cards: list[Card] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            term, _, definition = line.partition("\t")
        elif " - " in line:
            term, _, definition = line.partition(" - ")
        else:
            continue
        term, definition = _clean(term), _clean(definition)
        if term and definition:
            cards.append(Card(term[:MAX_CARD_TEXT], definition[:MAX_CARD_TEXT]))
    return cards
