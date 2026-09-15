"""Minimal, dependency-free PDF text extraction with positions.

This module exists so the flashcard importer can read the PDF that a browser
produces when a Quizlet print page is saved with "Save as PDF". It is not a
general-purpose PDF library; it is a tolerant reader for the subset of PDF
that browsers (Chrome/Skia, Firefox/cairo, Safari/Quartz) and common PDF
writers emit for text documents:

* classic xref tables, xref streams, and object streams (PDF 1.5+)
* FlateDecode streams (with PNG predictors)
* simple fonts (Type1/TrueType, 1-byte codes) and composite Type0 fonts with
  Identity encodings (2-byte codes), decoded through ToUnicode CMaps when
  present
* text positioning operators plus q/Q/cm so each text run has a device
  position, and horizontal/vertical filled rectangles or line segments
  (table borders) so callers can reconstruct table rows and columns

Everything degrades gracefully: unknown filters, fonts, and operators are
skipped rather than raising.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterator


class PDFParseError(Exception):
    """Raised when the document cannot be read at all."""


# ---------------------------------------------------------------------------
# Object model
# ---------------------------------------------------------------------------
class Name(str):
    """A PDF name object (``/Foo``)."""

    __slots__ = ()


class Keyword(str):
    """A bare keyword / content-stream operator."""

    __slots__ = ()


@dataclass(frozen=True)
class Ref:
    num: int
    gen: int


@dataclass
class Stream:
    dictionary: dict[str, Any]
    raw: bytes


WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"
_TOKEN_END = WHITESPACE + DELIMITERS
_NUMBER_RE = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")


class Lexer:
    """Tokenises and parses PDF object syntax from a bytes buffer."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos
        self.length = len(data)

    # -- low level ----------------------------------------------------------
    def skip_whitespace(self) -> None:
        data = self.data
        while self.pos < self.length:
            char = data[self.pos]
            if char in WHITESPACE:
                self.pos += 1
            elif char == 0x25:  # % comment
                while self.pos < self.length and data[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                break

    def next_token(self) -> Any:
        """Return the next token. Returns ``None`` at end of data."""
        self.skip_whitespace()
        if self.pos >= self.length:
            return None
        data = self.data
        char = data[self.pos]
        if char == 0x2F:  # /Name
            self.pos += 1
            start = self.pos
            while self.pos < self.length and data[self.pos] not in _TOKEN_END:
                self.pos += 1
            raw = data[start:self.pos]
            if b"#" in raw:
                raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), raw)
            return Name(raw.decode("latin-1"))
        if char == 0x28:  # (string)
            return self._literal_string()
        if char == 0x3C:  # < or <<
            if data[self.pos + 1:self.pos + 2] == b"<":
                self.pos += 2
                return Keyword("<<")
            return self._hex_string()
        if char == 0x3E:
            if data[self.pos + 1:self.pos + 2] == b">":
                self.pos += 2
                return Keyword(">>")
            self.pos += 1
            return Keyword(">")
        if char in b"[]{}":
            self.pos += 1
            return Keyword(chr(char))
        if char == 0x29:  # stray )
            self.pos += 1
            return Keyword(")")
        match = _NUMBER_RE.match(data, self.pos)
        if match and match.end() > self.pos:
            self.pos = match.end()
            text = match.group(0)
            try:
                if b"." in text:
                    return float(text)
                return int(text)
            except ValueError:
                return 0
        start = self.pos
        while self.pos < self.length and data[self.pos] not in _TOKEN_END:
            self.pos += 1
        if self.pos == start:
            self.pos += 1
            return Keyword(chr(char))
        return Keyword(data[start:self.pos].decode("latin-1"))

    def _literal_string(self) -> bytes:
        data = self.data
        self.pos += 1
        depth = 1
        out = bytearray()
        while self.pos < self.length:
            char = data[self.pos]
            self.pos += 1
            if char == 0x5C:  # backslash
                if self.pos >= self.length:
                    break
                nxt = data[self.pos]
                self.pos += 1
                if nxt in b"01234567":
                    digits = bytes([nxt])
                    for _ in range(2):
                        if self.pos < self.length and data[self.pos] in b"01234567":
                            digits += bytes([data[self.pos]])
                            self.pos += 1
                    out.append(int(digits, 8) & 0xFF)
                elif nxt == 0x6E:
                    out.append(0x0A)
                elif nxt == 0x72:
                    out.append(0x0D)
                elif nxt == 0x74:
                    out.append(0x09)
                elif nxt == 0x62:
                    out.append(0x08)
                elif nxt == 0x66:
                    out.append(0x0C)
                elif nxt == 0x0D:
                    if self.pos < self.length and data[self.pos] == 0x0A:
                        self.pos += 1
                elif nxt == 0x0A:
                    pass
                else:
                    out.append(nxt)
            elif char == 0x28:
                depth += 1
                out.append(char)
            elif char == 0x29:
                depth -= 1
                if depth == 0:
                    break
                out.append(char)
            else:
                out.append(char)
        return bytes(out)

    def _hex_string(self) -> bytes:
        data = self.data
        self.pos += 1
        start = self.pos
        end = data.find(b">", start)
        if end == -1:
            end = self.length
        self.pos = end + 1
        hex_digits = re.sub(rb"[^0-9A-Fa-f]", b"", data[start:end])
        if len(hex_digits) % 2:
            hex_digits += b"0"
        try:
            return bytes.fromhex(hex_digits.decode("ascii"))
        except ValueError:
            return b""

    # -- object level -------------------------------------------------------
    def parse_object(self, token: Any = ...) -> Any:
        """Parse one object. Handles ``R`` references by look-ahead."""
        if token is ...:
            token = self.next_token()
        if token is None:
            return None
        if isinstance(token, Keyword):
            if token == "<<":
                return self._parse_dict()
            if token == "[":
                return self._parse_array()
            if token == "true":
                return True
            if token == "false":
                return False
            if token == "null":
                return None
            return token
        if isinstance(token, int) and not isinstance(token, bool):
            # Possible "num gen R" reference.
            save = self.pos
            second = self.next_token()
            if isinstance(second, int) and not isinstance(second, bool) and second >= 0:
                save2 = self.pos
                third = self.next_token()
                if isinstance(third, Keyword) and third == "R":
                    return Ref(token, second)
                self.pos = save2
                self.pos = save
                return token
            self.pos = save
            return token
        return token

    def _parse_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while True:
            token = self.next_token()
            if token is None:
                break
            if isinstance(token, Keyword) and token == ">>":
                break
            if not isinstance(token, Name):
                # Malformed: skip value-ish token and continue.
                if isinstance(token, Keyword) and token in ("<<", "["):
                    self.parse_object(token)
                continue
            value = self.parse_object()
            if isinstance(value, Keyword) and value == ">>":
                result[str(token)] = None
                break
            result[str(token)] = value
        return result

    def _parse_array(self) -> list[Any]:
        result: list[Any] = []
        while True:
            token = self.next_token()
            if token is None:
                break
            if isinstance(token, Keyword):
                if token == "]":
                    break
                if token == ">>" or token == "}":
                    continue
            result.append(self.parse_object(token))
        return result


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def _apply_png_predictor(data: bytes, colors: int, bpc: int, columns: int) -> bytes:
    bpp = max(1, (colors * bpc + 7) // 8)
    row_len = (columns * colors * bpc + 7) // 8
    out = bytearray()
    prev = bytearray(row_len)
    pos = 0
    while pos + 1 <= len(data):
        filter_type = data[pos]
        pos += 1
        row = bytearray(data[pos:pos + row_len])
        if len(row) < row_len:
            row.extend(b"\x00" * (row_len - len(row)))
        pos += row_len
        if filter_type == 1:
            for i in range(bpp, row_len):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif filter_type == 2:
            for i in range(row_len):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(row_len):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(row_len):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pred) & 0xFF
        out.extend(row)
        prev = row
    return bytes(out)


def _flate(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except zlib.error:
        pass
    # Tolerate truncated / trailing-garbage streams.
    decompressor = zlib.decompressobj()
    try:
        return decompressor.decompress(data)
    except zlib.error:
        try:
            return zlib.decompressobj(-15).decompress(data)
        except zlib.error:
            return b""


def _ascii_hex(data: bytes) -> bytes:
    end = data.find(b">")
    if end != -1:
        data = data[:end]
    hex_digits = re.sub(rb"[^0-9A-Fa-f]", b"", data)
    if len(hex_digits) % 2:
        hex_digits += b"0"
    try:
        return bytes.fromhex(hex_digits.decode("ascii"))
    except ValueError:
        return b""


def _ascii85(data: bytes) -> bytes:
    import base64

    data = data.strip()
    if data.startswith(b"<~"):
        data = data[2:]
    end = data.find(b"~>")
    if end != -1:
        data = data[:end]
    data = re.sub(rb"\s", b"", data)
    try:
        return base64.a85decode(data)
    except (ValueError, TypeError):
        return b""


def _run_length(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        length = data[i]
        i += 1
        if length == 128:
            break
        if length < 128:
            out.extend(data[i:i + length + 1])
            i += length + 1
        else:
            if i < len(data):
                out.extend(bytes([data[i]]) * (257 - length))
            i += 1
    return bytes(out)


UNSUPPORTED_FILTERS = {"DCTDecode", "JPXDecode", "CCITTFaxDecode", "JBIG2Decode", "LZWDecode"}


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
_OBJ_RE = re.compile(rb"(?<![0-9])(\d{1,10})[ \t\r\n\x0c\x00]+(\d{1,5})[ \t\r\n\x0c\x00]+obj\b")
_STREAM_START_RE = re.compile(rb"stream(?:\r\n|\n|\r)")


class PDFDocument:
    """Loads a PDF and gives access to resolved objects and pages."""

    def __init__(self, data: bytes):
        if not isinstance(data, (bytes, bytearray)):
            raise PDFParseError("PDF data must be bytes.")
        self.data = bytes(data)
        if b"%PDF" not in self.data[:1024]:
            raise PDFParseError("The file does not look like a PDF document.")
        self._offsets: dict[int, int] = {}
        self._cache: dict[int, Any] = {}
        self._objstm_members: dict[int, tuple[int, int]] = {}  # objnum -> (container objnum, index)
        self._objstm_cache: dict[int, dict[int, Any]] = {}
        self.trailer: dict[str, Any] = {}
        self._scan_objects()
        self._load_trailer()
        self._expand_object_streams()
        if self.trailer.get("Encrypt") is not None:
            raise PDFParseError("This PDF is encrypted. Save an unencrypted copy and try again.")

    # -- object table -------------------------------------------------------
    def _scan_objects(self) -> None:
        for match in _OBJ_RE.finditer(self.data):
            num = int(match.group(1))
            # Later definitions win (incremental updates append to the file).
            self._offsets[num] = match.end()
        if not self._offsets:
            raise PDFParseError("No PDF objects could be found in the file.")

    def _load_trailer(self) -> None:
        merged: dict[str, Any] = {}
        for match in re.finditer(rb"trailer", self.data):
            lexer = Lexer(self.data, match.end())
            obj = lexer.parse_object()
            if isinstance(obj, dict):
                for key, value in obj.items():
                    merged.setdefault(key, value)
        # Cross-reference streams carry the trailer keys in their dictionary.
        for num in list(self._offsets):
            try:
                obj = self.get_object(num)
            except Exception:
                continue
            if isinstance(obj, Stream) and obj.dictionary.get("Type") == "XRef":
                for key in ("Root", "Info", "Encrypt", "ID"):
                    if key in obj.dictionary and key not in merged:
                        merged[key] = obj.dictionary[key]
        self.trailer = merged

    def _expand_object_streams(self) -> None:
        for num in list(self._offsets):
            try:
                obj = self.get_object(num)
            except Exception:
                continue
            if isinstance(obj, Stream) and obj.dictionary.get("Type") == "ObjStm":
                try:
                    members = self._parse_object_stream(num, obj)
                except Exception:
                    continue
                for member_num in members:
                    # Direct objects that appear later in the file than the
                    # container are newer; otherwise the stream member wins.
                    direct_offset = self._offsets.get(member_num)
                    if direct_offset is not None and direct_offset > self._offsets[num]:
                        continue
                    self._objstm_members[member_num] = (num, 0)
                    self._cache.pop(member_num, None)

    def _parse_object_stream(self, container_num: int, stream: Stream) -> dict[int, Any]:
        if container_num in self._objstm_cache:
            return self._objstm_cache[container_num]
        content = self.stream_data(stream)
        count = int(self.resolve(stream.dictionary.get("N", 0)) or 0)
        first = int(self.resolve(stream.dictionary.get("First", 0)) or 0)
        header = Lexer(content[:first])
        members: dict[int, Any] = {}
        pairs: list[tuple[int, int]] = []
        for _ in range(count):
            num = header.next_token()
            offset = header.next_token()
            if not isinstance(num, int) or not isinstance(offset, int):
                break
            pairs.append((num, offset))
        for num, offset in pairs:
            lexer = Lexer(content, first + offset)
            try:
                members[num] = lexer.parse_object()
            except Exception:
                members[num] = None
        self._objstm_cache[container_num] = members
        return members

    def get_object(self, num: int) -> Any:
        if num in self._cache:
            return self._cache[num]
        self._cache[num] = None  # cycle guard
        value: Any = None
        if num in self._objstm_members:
            container, _ = self._objstm_members[num]
            try:
                container_obj = self.get_object(container)
                if isinstance(container_obj, Stream):
                    value = self._parse_object_stream(container, container_obj).get(num)
            except Exception:
                value = None
        elif num in self._offsets:
            value = self._parse_indirect(self._offsets[num])
        self._cache[num] = value
        return value

    def _parse_indirect(self, offset: int) -> Any:
        lexer = Lexer(self.data, offset)
        obj = lexer.parse_object()
        if isinstance(obj, Keyword) and obj == "endobj":
            return None
        lexer.skip_whitespace()
        if isinstance(obj, dict) and self.data.startswith(b"stream", lexer.pos):
            match = _STREAM_START_RE.match(self.data, lexer.pos)
            start = match.end() if match else lexer.pos + len(b"stream")
            length = self.resolve(obj.get("Length"))
            end = -1
            if isinstance(length, int) and not isinstance(length, bool) and length >= 0 and start + length <= len(self.data):
                end = start + length
                tail = self.data[end:end + 20]
                if b"endstream" not in tail:
                    end = -1
            if end == -1:
                end = self.data.find(b"endstream", start)
                if end == -1:
                    end = len(self.data)
                # Strip the EOL that precedes endstream.
                if self.data[end - 2:end] == b"\r\n":
                    end -= 2
                elif self.data[end - 1:end] in (b"\n", b"\r"):
                    end -= 1
            return Stream(obj, self.data[start:end])
        return obj

    def resolve(self, value: Any, depth: int = 0) -> Any:
        while isinstance(value, Ref) and depth < 32:
            value = self.get_object(value.num)
            depth += 1
        return value

    # -- streams ------------------------------------------------------------
    def stream_data(self, stream: Stream) -> bytes:
        filters = self.resolve(stream.dictionary.get("Filter"))
        params = self.resolve(stream.dictionary.get("DecodeParms"))
        if filters is None:
            filters = []
        elif not isinstance(filters, list):
            filters = [filters]
        if params is None:
            params = [None] * len(filters)
        elif not isinstance(params, list):
            params = [params]
        data = stream.raw
        for index, filter_name in enumerate(filters):
            filter_name = str(self.resolve(filter_name) or "")
            parm = self.resolve(params[index]) if index < len(params) else None
            parm = parm if isinstance(parm, dict) else {}
            if filter_name in ("FlateDecode", "Fl"):
                data = _flate(data)
            elif filter_name in ("ASCIIHexDecode", "AHx"):
                data = _ascii_hex(data)
            elif filter_name in ("ASCII85Decode", "A85"):
                data = _ascii85(data)
            elif filter_name in ("RunLengthDecode", "RL"):
                data = _run_length(data)
            elif filter_name in UNSUPPORTED_FILTERS or filter_name == "Crypt":
                return b""
            else:
                return b""
            predictor = self.resolve(parm.get("Predictor", 1))
            if isinstance(predictor, int) and predictor >= 10:
                colors = int(self.resolve(parm.get("Colors", 1)) or 1)
                bpc = int(self.resolve(parm.get("BitsPerComponent", 8)) or 8)
                columns = int(self.resolve(parm.get("Columns", 1)) or 1)
                data = _apply_png_predictor(data, colors, bpc, columns)
        return data

    # -- pages --------------------------------------------------------------
    def _catalog(self) -> dict[str, Any] | None:
        root = self.resolve(self.trailer.get("Root"))
        if isinstance(root, dict) and root.get("Type") in ("Catalog", None) and "Pages" in root:
            return root
        for num in sorted(self._all_object_numbers()):
            obj = self.resolve(self.get_object(num))
            if isinstance(obj, dict) and obj.get("Type") == "Catalog":
                return obj
        return None

    def _all_object_numbers(self) -> set[int]:
        return set(self._offsets) | set(self._objstm_members)

    def pages(self) -> list[dict[str, Any]]:
        """Return page dictionaries in document order with inherited attributes merged."""
        catalog = self._catalog()
        pages: list[dict[str, Any]] = []
        seen: set[int] = set()
        inheritable = ("Resources", "MediaBox", "CropBox", "Rotate")

        def walk(node_ref: Any, inherited: dict[str, Any], depth: int) -> None:
            if depth > 64:
                return
            if isinstance(node_ref, Ref):
                if node_ref.num in seen:
                    return
                seen.add(node_ref.num)
            node = self.resolve(node_ref)
            if not isinstance(node, dict):
                return
            merged = dict(inherited)
            for key in inheritable:
                if key in node:
                    merged[key] = node[key]
            node_type = node.get("Type")
            kids = self.resolve(node.get("Kids"))
            if node_type == "Page" or (node_type != "Pages" and kids is None and "Contents" in node):
                page = dict(node)
                page.update({key: value for key, value in merged.items() if key not in page})
                pages.append(page)
                return
            if isinstance(kids, list):
                for kid in kids:
                    walk(kid, merged, depth + 1)

        if catalog is not None:
            walk(catalog.get("Pages"), {}, 0)
        if not pages:
            # Fall back to scanning for page objects when the tree is damaged.
            for num in sorted(self._all_object_numbers()):
                obj = self.resolve(self.get_object(num))
                if isinstance(obj, dict) and obj.get("Type") == "Page":
                    page = dict(obj)
                    parent = self.resolve(obj.get("Parent"))
                    hops = 0
                    while isinstance(parent, dict) and hops < 32:
                        for key in inheritable:
                            if key not in page and key in parent:
                                page[key] = parent[key]
                        parent = self.resolve(parent.get("Parent"))
                        hops += 1
                    pages.append(page)
        return pages

    def page_content(self, page: dict[str, Any]) -> bytes:
        contents = self.resolve(page.get("Contents"))
        if isinstance(contents, Stream):
            return self.stream_data(contents)
        if isinstance(contents, list):
            chunks = []
            for item in contents:
                stream = self.resolve(item)
                if isinstance(stream, Stream):
                    chunks.append(self.stream_data(stream))
            return b"\n".join(chunks)
        return b""


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_GLYPH_NAMES = {
    "space": " ", "exclam": "!", "quotedbl": '"', "numbersign": "#", "dollar": "$", "percent": "%",
    "ampersand": "&", "quotesingle": "'", "quoteright": "\u2019", "quoteleft": "\u2018", "parenleft": "(",
    "parenright": ")", "asterisk": "*", "plus": "+", "comma": ",", "hyphen": "-", "minus": "\u2212",
    "period": ".", "slash": "/", "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "colon": ":", "semicolon": ";", "less": "<",
    "equal": "=", "greater": ">", "question": "?", "at": "@", "bracketleft": "[", "backslash": "\\",
    "bracketright": "]", "asciicircum": "^", "underscore": "_", "grave": "`", "braceleft": "{", "bar": "|",
    "braceright": "}", "asciitilde": "~", "endash": "\u2013", "emdash": "\u2014", "quotedblleft": "\u201c",
    "quotedblright": "\u201d", "quotesinglbase": "\u201a", "quotedblbase": "\u201e", "bullet": "\u2022",
    "ellipsis": "\u2026", "degree": "\u00b0", "periodcentered": "\u00b7", "multiply": "\u00d7",
    "divide": "\u00f7", "fi": "fi", "fl": "fl", "ff": "ff", "ffi": "ffi", "ffl": "ffl", "copyright": "\u00a9",
    "registered": "\u00ae", "trademark": "\u2122", "section": "\u00a7", "paragraph": "\u00b6",
    "eacute": "\u00e9", "egrave": "\u00e8", "ecircumflex": "\u00ea", "edieresis": "\u00eb", "agrave": "\u00e0",
    "aacute": "\u00e1", "acircumflex": "\u00e2", "adieresis": "\u00e4", "ccedilla": "\u00e7", "ntilde": "\u00f1",
    "ocircumflex": "\u00f4", "odieresis": "\u00f6", "ograve": "\u00f2", "oacute": "\u00f3", "ucircumflex": "\u00fb",
    "udieresis": "\u00fc", "ugrave": "\u00f9", "uacute": "\u00fa", "idieresis": "\u00ef", "icircumflex": "\u00ee",
    "iacute": "\u00ed", "igrave": "\u00ec", "Eacute": "\u00c9", "Agrave": "\u00c0", "Ccedilla": "\u00c7",
    "sterling": "\u00a3", "Euro": "\u20ac", "yen": "\u00a5", "cent": "\u00a2", "plusminus": "\u00b1",
    "onehalf": "\u00bd", "onequarter": "\u00bc", "threequarters": "\u00be", "mu": "\u00b5", "arrowright": "\u2192",
    "arrowleft": "\u2190", "checkmark": "\u2713", "nbspace": "\u00a0", "hyphenminus": "-", "sfthyphen": "\u00ad",
}
_UNI_RE = re.compile(r"^uni([0-9A-Fa-f]{4,6})$")
_U_RE = re.compile(r"^u([0-9A-Fa-f]{4,6})$")


def _glyph_name_to_text(name: str) -> str | None:
    if name in _GLYPH_NAMES:
        return _GLYPH_NAMES[name]
    if len(name) == 1:
        return name
    match = _UNI_RE.match(name) or _U_RE.match(name)
    if match:
        try:
            return "".join(chr(int(match.group(1)[i:i + 4], 16)) for i in range(0, len(match.group(1)), 4))
        except ValueError:
            return None
    base = name.split(".")[0]
    if base != name and base:
        return _glyph_name_to_text(base)
    match = re.match(r"^(?:g|cid|c|G)(\d+)$", name)
    if match:
        return None
    return None


def _utf16be(data: bytes) -> str:
    if len(data) % 2:
        data = data + b"\x00"
    try:
        return data.decode("utf-16-be", errors="replace")
    except Exception:
        return ""


def parse_tounicode(cmap_bytes: bytes) -> tuple[dict[int, str], list[tuple[int, int, int]]]:
    """Return (code -> text mapping, codespace byte-length ranges)."""
    mapping: dict[int, str] = {}
    codespaces: list[tuple[int, int, int]] = []  # (low, high, byte length)
    lexer = Lexer(cmap_bytes)
    stack: list[Any] = []
    while True:
        token = lexer.next_token()
        if token is None:
            break
        if isinstance(token, Keyword):
            if token == "begincodespacerange":
                while True:
                    low = lexer.next_token()
                    if low is None or (isinstance(low, Keyword) and low == "endcodespacerange"):
                        break
                    high = lexer.next_token()
                    if isinstance(low, bytes) and isinstance(high, bytes) and low:
                        codespaces.append((int.from_bytes(low, "big"), int.from_bytes(high, "big"), len(low)))
                stack.clear()
            elif token == "beginbfchar":
                while True:
                    src = lexer.next_token()
                    if src is None or (isinstance(src, Keyword) and src == "endbfchar"):
                        break
                    dst = lexer.parse_object()
                    if isinstance(src, bytes) and src:
                        code = int.from_bytes(src, "big")
                        if isinstance(dst, bytes):
                            mapping[code] = _utf16be(dst)
                        elif isinstance(dst, Name):
                            text = _glyph_name_to_text(str(dst))
                            if text:
                                mapping[code] = text
                stack.clear()
            elif token == "beginbfrange":
                while True:
                    low = lexer.next_token()
                    if low is None or (isinstance(low, Keyword) and low == "endbfrange"):
                        break
                    high = lexer.next_token()
                    dst = lexer.parse_object()
                    if not (isinstance(low, bytes) and isinstance(high, bytes) and low):
                        continue
                    lo = int.from_bytes(low, "big")
                    hi = int.from_bytes(high, "big")
                    if hi < lo:
                        lo, hi = hi, lo
                    if hi - lo > 65535:
                        hi = lo + 65535
                    if isinstance(dst, list):
                        for offset, item in enumerate(dst):
                            if lo + offset > hi:
                                break
                            if isinstance(item, bytes):
                                mapping[lo + offset] = _utf16be(item)
                    elif isinstance(dst, bytes) and dst:
                        base_text = _utf16be(dst)
                        if not base_text:
                            continue
                        prefix, last = base_text[:-1], base_text[-1]
                        last_ord = ord(last)
                        for code in range(lo, hi + 1):
                            try:
                                mapping[code] = prefix + chr(last_ord + (code - lo))
                            except (ValueError, OverflowError):
                                break
                stack.clear()
            else:
                stack.clear()
        else:
            stack.append(token)
            if len(stack) > 64:
                del stack[:32]
    return mapping, codespaces


# Approximate widths (per 1000 em) for text when a font supplies none.
_DEFAULT_SIMPLE_WIDTH = 500


@dataclass
class Font:
    name: str = ""
    subtype: str = ""
    two_byte: bool = False
    codespaces: list[tuple[int, int, int]] = field(default_factory=list)
    to_unicode: dict[int, str] = field(default_factory=dict)
    encoding_map: dict[int, str] = field(default_factory=dict)
    widths: dict[int, float] = field(default_factory=dict)
    default_width: float = _DEFAULT_SIMPLE_WIDTH
    is_type3: bool = False
    font_matrix: tuple[float, ...] = (0.001, 0, 0, 0.001, 0, 0)

    def iter_codes(self, data: bytes) -> Iterator[tuple[int, int]]:
        """Yield (code, byte_length) for a string shown with this font."""
        if self.codespaces:
            pos = 0
            lengths = sorted({length for _, _, length in self.codespaces})
            while pos < len(data):
                matched = False
                for length in lengths:
                    chunk = data[pos:pos + length]
                    if len(chunk) < length:
                        continue
                    code = int.from_bytes(chunk, "big")
                    for low, high, cs_len in self.codespaces:
                        if cs_len == length and low <= code <= high:
                            yield code, length
                            pos += length
                            matched = True
                            break
                    if matched:
                        break
                if not matched:
                    length = lengths[0] if lengths else (2 if self.two_byte else 1)
                    chunk = data[pos:pos + length]
                    yield int.from_bytes(chunk, "big"), len(chunk) or 1
                    pos += max(1, len(chunk))
            return
        step = 2 if self.two_byte else 1
        for pos in range(0, len(data), step):
            chunk = data[pos:pos + step]
            yield int.from_bytes(chunk, "big"), len(chunk)

    def decode(self, code: int, length: int) -> str:
        if code in self.to_unicode:
            return self.to_unicode[code]
        if code in self.encoding_map:
            return self.encoding_map[code]
        if length == 1 and not self.two_byte:
            if code == 0xA0:
                return " "
            if 32 <= code < 127 or code >= 160:
                try:
                    return bytes([code]).decode("cp1252")
                except UnicodeDecodeError:
                    return chr(code)
            if code in (9, 10, 13):
                return " "
            return ""
        return ""

    def width(self, code: int) -> float:
        """Glyph advance in text space units (already divided by 1000 for non-Type3)."""
        raw = self.widths.get(code, self.default_width)
        if self.is_type3:
            return raw * self.font_matrix[0]
        return raw / 1000.0


class FontLoader:
    def __init__(self, doc: PDFDocument):
        self.doc = doc
        self._cache: dict[Any, Font] = {}

    def load(self, font_ref: Any) -> Font:
        cache_key = font_ref if isinstance(font_ref, Ref) else id(font_ref)
        if cache_key in self._cache:
            return self._cache[cache_key]
        font = Font()
        try:
            self._populate(font, self.doc.resolve(font_ref))
        except Exception:
            pass
        self._cache[cache_key] = font
        return font

    def _populate(self, font: Font, fd: Any) -> None:
        doc = self.doc
        if not isinstance(fd, dict):
            return
        font.subtype = str(doc.resolve(fd.get("Subtype")) or "")
        font.name = str(doc.resolve(fd.get("BaseFont")) or "")
        to_unicode = doc.resolve(fd.get("ToUnicode"))
        if isinstance(to_unicode, Stream):
            mapping, codespaces = parse_tounicode(doc.stream_data(to_unicode))
            font.to_unicode = mapping
            font.codespaces = codespaces
        if font.subtype == "Type0":
            font.two_byte = True
            encoding = doc.resolve(fd.get("Encoding"))
            if isinstance(encoding, Stream):
                _, cs = parse_tounicode(doc.stream_data(encoding))
                if cs and not font.codespaces:
                    font.codespaces = cs
            descendants = doc.resolve(fd.get("DescendantFonts")) or []
            descendant = doc.resolve(descendants[0]) if isinstance(descendants, list) and descendants else None
            if isinstance(descendant, dict):
                font.default_width = float(doc.resolve(descendant.get("DW", 1000)) or 1000)
                widths = doc.resolve(descendant.get("W"))
                if isinstance(widths, list):
                    self._parse_cid_widths(font, widths)
            if font.codespaces and all(length == 1 for _, _, length in font.codespaces):
                # A ToUnicode CMap advertised 1-byte codes for a Type0 font; trust the font.
                font.codespaces = []
            return
        if font.subtype == "Type3":
            font.is_type3 = True
            matrix = doc.resolve(fd.get("FontMatrix"))
            if isinstance(matrix, list) and len(matrix) == 6:
                try:
                    font.font_matrix = tuple(float(doc.resolve(v)) for v in matrix)
                except (TypeError, ValueError):
                    pass
        font.two_byte = False
        font.codespaces = [cs for cs in font.codespaces if cs[2] == 1]
        first_char = doc.resolve(fd.get("FirstChar", 0))
        widths = doc.resolve(fd.get("Widths"))
        if isinstance(widths, list) and isinstance(first_char, int):
            for index, value in enumerate(widths):
                value = doc.resolve(value)
                if isinstance(value, (int, float)):
                    font.widths[first_char + index] = float(value)
            descriptor = doc.resolve(fd.get("FontDescriptor"))
            missing = doc.resolve(descriptor.get("MissingWidth", 0)) if isinstance(descriptor, dict) else 0
            font.default_width = float(missing or 0) if font.widths else _DEFAULT_SIMPLE_WIDTH
            if font.is_type3:
                font.default_width = 0.0
        encoding = doc.resolve(fd.get("Encoding"))
        base_map: dict[int, str] = {}
        if isinstance(encoding, dict):
            differences = doc.resolve(encoding.get("Differences"))
            if isinstance(differences, list):
                code = 0
                for item in differences:
                    item = doc.resolve(item)
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        code = int(item)
                    elif isinstance(item, Name):
                        text = _glyph_name_to_text(str(item))
                        if text is not None:
                            base_map[code] = text
                        code += 1
        font.encoding_map = base_map

    def _parse_cid_widths(self, font: Font, widths: list[Any]) -> None:
        doc = self.doc
        items = [doc.resolve(item) for item in widths]
        index = 0
        while index < len(items):
            first = items[index]
            if not isinstance(first, (int, float)):
                index += 1
                continue
            if index + 1 < len(items) and isinstance(items[index + 1], list):
                for offset, value in enumerate(items[index + 1]):
                    value = doc.resolve(value)
                    if isinstance(value, (int, float)):
                        font.widths[int(first) + offset] = float(value)
                index += 2
            elif index + 2 < len(items) and isinstance(items[index + 1], (int, float)) and isinstance(items[index + 2], (int, float)):
                start, end, value = int(first), int(items[index + 1]), float(items[index + 2])
                if end - start > 65535:
                    end = start + 65535
                for code in range(start, end + 1):
                    font.widths[code] = value
                index += 3
            else:
                index += 1


# ---------------------------------------------------------------------------
# Content stream interpretation
# ---------------------------------------------------------------------------
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mat_mul(m: Matrix, n: Matrix) -> Matrix:
    """Return m × n (apply m first, then n) using PDF row-vector conventions."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


@dataclass
class TextRun:
    """A run of text drawn with a single font and baseline."""

    text: str
    x0: float
    x1: float
    y: float
    size: float
    font: str = ""


@dataclass
class Rule:
    """A thin horizontal or vertical stroke/fill (table border)."""

    orientation: str  # "h" or "v"
    position: float  # y for horizontal, x for vertical
    start: float
    end: float
    thickness: float


@dataclass
class PageText:
    width: float
    height: float
    runs: list[TextRun]
    rules: list[Rule]


class _GraphicsState:
    __slots__ = ("ctm", "font", "size", "char_spacing", "word_spacing", "hscale", "leading", "rise")

    def __init__(self, ctm: Matrix):
        self.ctm = ctm
        self.font: Font | None = None
        self.size = 0.0
        self.char_spacing = 0.0
        self.word_spacing = 0.0
        self.hscale = 1.0
        self.leading = 0.0
        self.rise = 0.0

    def copy(self) -> "_GraphicsState":
        clone = _GraphicsState(self.ctm)
        clone.font = self.font
        clone.size = self.size
        clone.char_spacing = self.char_spacing
        clone.word_spacing = self.word_spacing
        clone.hscale = self.hscale
        clone.leading = self.leading
        clone.rise = self.rise
        return clone


class ContentInterpreter:
    MAX_OPS = 2_000_000
    MAX_FORM_DEPTH = 8

    def __init__(self, doc: PDFDocument, fonts: FontLoader):
        self.doc = doc
        self.fonts = fonts
        self.runs: list[TextRun] = []
        self.rules: list[Rule] = []
        self._ops = 0

    def run(self, content: bytes, resources: Any, base_ctm: Matrix) -> None:
        self._execute(content, self.doc.resolve(resources) or {}, base_ctm, 0)

    # -- helpers --------------------------------------------------------------
    def _font_dict(self, resources: dict[str, Any], name: str) -> Any:
        fonts = self.doc.resolve(resources.get("Font")) if isinstance(resources, dict) else None
        if isinstance(fonts, dict):
            return fonts.get(name)
        return None

    def _xobject(self, resources: dict[str, Any], name: str) -> Any:
        xobjects = self.doc.resolve(resources.get("XObject")) if isinstance(resources, dict) else None
        if isinstance(xobjects, dict):
            return self.doc.resolve(xobjects.get(name))
        return None

    def _record_rect(self, ctm: Matrix, x: float, y: float, w: float, h: float) -> None:
        corners = [apply(ctm, x, y), apply(ctm, x + w, y), apply(ctm, x + w, y + h), apply(ctm, x, y + h)]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if height <= 4.0 and width >= 12.0:
            self.rules.append(Rule("h", (min(ys) + max(ys)) / 2, min(xs), max(xs), height))
        elif width <= 4.0 and height >= 12.0:
            self.rules.append(Rule("v", (min(xs) + max(xs)) / 2, min(ys), max(ys), width))

    def _record_segment(self, p0: tuple[float, float], p1: tuple[float, float]) -> None:
        dx = abs(p1[0] - p0[0])
        dy = abs(p1[1] - p0[1])
        if dy <= 1.5 and dx >= 12.0:
            self.rules.append(Rule("h", (p0[1] + p1[1]) / 2, min(p0[0], p1[0]), max(p0[0], p1[0]), 0.0))
        elif dx <= 1.5 and dy >= 12.0:
            self.rules.append(Rule("v", (p0[0] + p1[0]) / 2, min(p0[1], p1[1]), max(p0[1], p1[1]), 0.0))

    # -- main loop ------------------------------------------------------------
    def _execute(self, content: bytes, resources: dict[str, Any], base_ctm: Matrix, depth: int) -> None:
        lexer = Lexer(content)
        operands: list[Any] = []
        gs = _GraphicsState(base_ctm)
        stack: list[_GraphicsState] = []
        tm: Matrix = IDENTITY
        tlm: Matrix = IDENTITY
        current_point: tuple[float, float] | None = None
        pending_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        pending_rects: list[tuple[Matrix, float, float, float, float]] = []
        doc = self.doc

        def num(value: Any, default: float = 0.0) -> float:
            return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default

        def flush_paths(paint: bool) -> None:
            nonlocal pending_segments, pending_rects
            if paint:
                for ctm_, x, y, w, h in pending_rects:
                    self._record_rect(ctm_, x, y, w, h)
                for p0, p1 in pending_segments:
                    self._record_segment(p0, p1)
            pending_segments = []
            pending_rects = []

        def show_text(data: bytes) -> None:
            nonlocal tm
            font = gs.font
            if font is None:
                font = Font()
            size = gs.size
            trm = mat_mul((size * gs.hscale, 0.0, 0.0, size, 0.0, gs.rise), mat_mul(tm, gs.ctm))
            start_x, start_y = apply(trm, 0.0, 0.0)
            scale = (trm[0] ** 2 + trm[1] ** 2) ** 0.5 or abs(size)
            device_size = (trm[2] ** 2 + trm[3] ** 2) ** 0.5 or abs(size)
            pieces: list[str] = []
            advance = 0.0
            for code, length in font.iter_codes(data):
                glyph = font.decode(code, length)
                pieces.append(glyph)
                w0 = font.width(code)
                tx = (w0 * size + gs.char_spacing + (gs.word_spacing if (length == 1 and code == 32) else 0.0)) * gs.hscale
                advance += tx
            text = "".join(pieces)
            end_x, end_y = apply(mat_mul(tm, gs.ctm), advance, 0.0)
            tm = mat_mul((1.0, 0.0, 0.0, 1.0, advance, 0.0), tm)
            if text.strip() or text:
                self.runs.append(TextRun(text, start_x, end_x, start_y, device_size, font.name))
            _ = scale, end_y

        def adjust(amount: float) -> None:
            nonlocal tm
            tx = -amount / 1000.0 * gs.size * gs.hscale
            tm = mat_mul((1.0, 0.0, 0.0, 1.0, tx, 0.0), tm)

        while True:
            self._ops += 1
            if self._ops > self.MAX_OPS:
                return
            token = lexer.next_token()
            if token is None:
                break
            if isinstance(token, Keyword):
                if token == "<<":
                    operands.append(lexer.parse_object(token))
                    continue
                if token == "[":
                    operands.append(lexer.parse_object(token))
                    continue
                if token in ("true", "false", "null"):
                    operands.append(lexer.parse_object(token))
                    continue
                op = str(token)
                try:
                    if op == "q":
                        stack.append(gs.copy())
                        if len(stack) > 256:
                            stack.pop(0)
                    elif op == "Q":
                        if stack:
                            gs = stack.pop()
                    elif op == "cm" and len(operands) >= 6:
                        m = tuple(num(v) for v in operands[-6:])
                        gs.ctm = mat_mul(m, gs.ctm)  # type: ignore[arg-type]
                    elif op == "BT":
                        tm = IDENTITY
                        tlm = IDENTITY
                    elif op == "ET":
                        pass
                    elif op == "Tf" and len(operands) >= 2:
                        gs.size = num(operands[-1])
                        font_name = operands[-2]
                        font_ref = self._font_dict(resources, str(font_name)) if isinstance(font_name, Name) else None
                        gs.font = self.fonts.load(font_ref) if font_ref is not None else Font()
                    elif op == "Td" and len(operands) >= 2:
                        tlm = mat_mul((1.0, 0.0, 0.0, 1.0, num(operands[-2]), num(operands[-1])), tlm)
                        tm = tlm
                    elif op == "TD" and len(operands) >= 2:
                        gs.leading = -num(operands[-1])
                        tlm = mat_mul((1.0, 0.0, 0.0, 1.0, num(operands[-2]), num(operands[-1])), tlm)
                        tm = tlm
                    elif op == "Tm" and len(operands) >= 6:
                        tlm = tuple(num(v) for v in operands[-6:])  # type: ignore[assignment]
                        tm = tlm
                    elif op == "T*":
                        tlm = mat_mul((1.0, 0.0, 0.0, 1.0, 0.0, -gs.leading), tlm)
                        tm = tlm
                    elif op == "TL" and operands:
                        gs.leading = num(operands[-1])
                    elif op == "Tc" and operands:
                        gs.char_spacing = num(operands[-1])
                    elif op == "Tw" and operands:
                        gs.word_spacing = num(operands[-1])
                    elif op == "Tz" and operands:
                        gs.hscale = num(operands[-1], 100.0) / 100.0
                    elif op == "Ts" and operands:
                        gs.rise = num(operands[-1])
                    elif op == "Tj" and operands:
                        if isinstance(operands[-1], bytes):
                            show_text(operands[-1])
                    elif op == "'" and operands:
                        tlm = mat_mul((1.0, 0.0, 0.0, 1.0, 0.0, -gs.leading), tlm)
                        tm = tlm
                        if isinstance(operands[-1], bytes):
                            show_text(operands[-1])
                    elif op == '"' and len(operands) >= 3:
                        gs.word_spacing = num(operands[-3])
                        gs.char_spacing = num(operands[-2])
                        tlm = mat_mul((1.0, 0.0, 0.0, 1.0, 0.0, -gs.leading), tlm)
                        tm = tlm
                        if isinstance(operands[-1], bytes):
                            show_text(operands[-1])
                    elif op == "TJ" and operands:
                        array = operands[-1]
                        if isinstance(array, list):
                            for item in array:
                                if isinstance(item, bytes):
                                    show_text(item)
                                elif isinstance(item, (int, float)) and not isinstance(item, bool):
                                    # Large negative kerning is a visual space.
                                    if item < -180 and self.runs and gs.size:
                                        last = self.runs[-1]
                                        if last.text and not last.text.endswith(" "):
                                            last.text += " "
                                    adjust(float(item))
                    elif op == "Do" and operands and isinstance(operands[-1], Name):
                        if depth < self.MAX_FORM_DEPTH:
                            xobj = self._xobject(resources, str(operands[-1]))
                            if isinstance(xobj, Stream) and xobj.dictionary.get("Subtype") == "Form":
                                matrix = doc.resolve(xobj.dictionary.get("Matrix"))
                                form_ctm = gs.ctm
                                if isinstance(matrix, list) and len(matrix) == 6:
                                    form_ctm = mat_mul(tuple(num(doc.resolve(v)) for v in matrix), gs.ctm)  # type: ignore[arg-type]
                                form_resources = doc.resolve(xobj.dictionary.get("Resources")) or resources
                                saved_runs = len(self.runs)
                                self._execute(doc.stream_data(xobj), form_resources, form_ctm, depth + 1)
                                _ = saved_runs
                    # Path construction (for table borders)
                    elif op == "m" and len(operands) >= 2:
                        current_point = apply(gs.ctm, num(operands[-2]), num(operands[-1]))
                    elif op == "l" and len(operands) >= 2:
                        point = apply(gs.ctm, num(operands[-2]), num(operands[-1]))
                        if current_point is not None:
                            pending_segments.append((current_point, point))
                        current_point = point
                    elif op == "re" and len(operands) >= 4:
                        x, y, w, h = (num(v) for v in operands[-4:])
                        pending_rects.append((gs.ctm, x, y, w, h))
                        current_point = apply(gs.ctm, x, y)
                    elif op in ("c", "v", "y") and len(operands) >= 2:
                        current_point = apply(gs.ctm, num(operands[-2]), num(operands[-1]))
                    elif op in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*"):
                        flush_paths(True)
                    elif op == "n":
                        flush_paths(False)
                    elif op in ("W", "W*", "h"):
                        pass
                    elif op == "BI":
                        # Inline image: skip to EI.
                        end = content.find(b"EI", lexer.pos)
                        while end != -1 and not (content[end - 1:end] in WHITESPACE and content[end + 2:end + 3] in WHITESPACE + b""):
                            end = content.find(b"EI", end + 2)
                        lexer.pos = len(content) if end == -1 else end + 2
                except Exception:
                    pass
                operands = []
            else:
                operands.append(token)
                if len(operands) > 64:
                    del operands[:32]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _media_box(doc: PDFDocument, page: dict[str, Any]) -> tuple[float, float, float, float]:
    box = doc.resolve(page.get("MediaBox"))
    try:
        values = [float(doc.resolve(v)) for v in box]  # type: ignore[union-attr]
        if len(values) == 4:
            x0, y0, x1, y1 = values
            return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    except (TypeError, ValueError):
        pass
    return (0.0, 0.0, 612.0, 792.0)


def extract_pages(data: bytes, max_pages: int = 200) -> list[PageText]:
    """Extract positioned text runs and table borders from every page."""
    doc = PDFDocument(data)
    fonts = FontLoader(doc)
    pages = doc.pages()
    if not pages:
        raise PDFParseError("The PDF does not contain any readable pages.")
    results: list[PageText] = []
    for page in pages[:max_pages]:
        x0, y0, x1, y1 = _media_box(doc, page)
        width, height = x1 - x0, y1 - y0
        rotate = doc.resolve(page.get("Rotate", 0))
        base: Matrix = (1.0, 0.0, 0.0, 1.0, -x0, -y0)
        try:
            rotate = int(rotate or 0) % 360
        except (TypeError, ValueError):
            rotate = 0
        if rotate == 90:
            base = mat_mul(base, (0.0, -1.0, 1.0, 0.0, 0.0, width))
            width, height = height, width
        elif rotate == 180:
            base = mat_mul(base, (-1.0, 0.0, 0.0, -1.0, width, height))
        elif rotate == 270:
            base = mat_mul(base, (0.0, 1.0, -1.0, 0.0, height, 0.0))
            width, height = height, width
        interpreter = ContentInterpreter(doc, fonts)
        try:
            interpreter.run(doc.page_content(page), page.get("Resources"), base)
        except RecursionError:
            pass
        results.append(PageText(width, height, interpreter.runs, interpreter.rules))
    return results


def extract_text(data: bytes) -> str:
    """Convenience: plain text of the whole document, one line per baseline."""
    output: list[str] = []
    for page in extract_pages(data):
        lines: dict[int, list[TextRun]] = {}
        for run in page.runs:
            lines.setdefault(round(run.y), []).append(run)
        for y in sorted(lines, reverse=True):
            runs = sorted(lines[y], key=lambda r: r.x0)
            output.append(" ".join(run.text.strip() for run in runs if run.text.strip()))
        output.append("")
    return "\n".join(output).strip()
