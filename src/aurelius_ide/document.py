"""Document model for the research IDE.

The analysis engine needs a *structural* view of a paper, not a token stream: where the
citation sites are, which keys each one references, which BibTeX entries exist, and which
sentences make load-bearing empirical claims. This module turns raw ``.tex`` and ``.bib``
text into that view.

Two design constraints shaped it:

* **Stdlib only.** No TeX parser dependency. A full LaTeX grammar is undecidable in the
  general case (macros can redefine syntax), but the constructs we care about — ``\\cite``
  family, sectioning, math regions, comments — are lexically regular in every real paper.
  We parse those exactly and ignore everything else rather than pretending to understand
  the whole document.
* **Offsets are first-class.** Every parsed element carries a byte-offset span *and* an
  LSP-style ``(line, character)`` range, because diagnostics have to point at exact
  ranges in an editor. :class:`PositionIndex` does the conversion in O(log n).
"""
from __future__ import annotations

import hashlib
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------
# Positions
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """Zero-indexed (line, character) — matches the LSP wire format exactly."""

    line: int
    character: int


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position


class PositionIndex:
    """Converts absolute character offsets to ``(line, character)`` positions.

    Built once per document version. Uses a sorted list of line-start offsets and a
    binary search, so a document with n lines converts any offset in O(log n) — this
    matters because a paper with 400 citations produces hundreds of range conversions
    on every keystroke.
    """

    def __init__(self, text: str) -> None:
        self._line_starts: List[int] = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self._line_starts.append(i + 1)
        self._length = len(text)

    def position(self, offset: int) -> Position:
        offset = max(0, min(offset, self._length))
        line = bisect_right(self._line_starts, offset) - 1
        return Position(line=line, character=offset - self._line_starts[line])

    def range(self, start: int, end: int) -> Range:
        return Range(start=self.position(start), end=self.position(end))


# --------------------------------------------------------------------------------------
# Parsed elements
# --------------------------------------------------------------------------------------


@dataclass
class CiteKeyRef:
    """A single citation key inside a ``\\cite``-family command.

    ``\\citep{smith2020, jones2021}`` yields two of these, each with the span of just its
    own key — so an "undefined key" diagnostic underlines the offending key rather than
    the whole command.
    """

    key: str
    start: int
    end: int
    command: str  # 'cite', 'citep', 'citet', ...


@dataclass
class BibEntry:
    """A parsed BibTeX record."""

    key: str
    entry_type: str
    fields: Dict[str, str]
    start: int
    end: int

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def year(self) -> str:
        return self.fields.get("year", "")

    @property
    def author(self) -> str:
        return self.fields.get("author", "")

    @property
    def doi(self) -> str:
        return self.fields.get("doi", "")

    def as_citation_string(self) -> str:
        """Render the entry as a plain citation string for ``scholarly.verify_citation``.

        The verifier takes free text (it extracts DOI / title / author / year itself), so
        we reconstruct a conventional reference line rather than inventing a new contract.
        """
        bits: List[str] = []
        if self.author:
            bits.append(self.author.replace(" and ", ", "))
        if self.year:
            bits.append(f"({self.year})")
        if self.title:
            bits.append(self.title + ".")
        for name in ("journal", "booktitle", "publisher"):
            if self.fields.get(name):
                bits.append(self.fields[name] + ".")
                break
        if self.doi:
            bits.append(f"doi:{self.doi}")
        return " ".join(bits).strip()

    def content_hash(self) -> str:
        """Hash of the *semantic* fields only.

        Reformatting whitespace or reordering fields must not invalidate a cached
        verification result — only a change to what the entry actually claims should.
        """
        payload = "|".join(
            f"{k}={self.fields[k]}" for k in sorted(self.fields) if k in _SEMANTIC_FIELDS
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


_SEMANTIC_FIELDS = frozenset(
    {"title", "author", "year", "doi", "journal", "booktitle", "publisher", "volume", "pages"}
)


@dataclass
class Sentence:
    """A prose sentence outside math, comments, and verbatim regions."""

    text: str
    start: int
    end: int
    cite_keys: List[str] = field(default_factory=list)
    section: str = ""

    def content_hash(self) -> str:
        return hashlib.sha256(self.text.strip().encode("utf-8")).hexdigest()[:32]


@dataclass
class Section:
    title: str
    level: str  # 'chapter' | 'section' | 'subsection' | 'subsubsection'
    start: int
    end: int


# --------------------------------------------------------------------------------------
# LaTeX lexing
# --------------------------------------------------------------------------------------

# The \cite family. Optional args (\citep[see][p.~4]{key}) are consumed before the
# mandatory key group.
_CITE_RE = re.compile(
    r"\\(?P<cmd>cite[a-zA-Z]*|nocite)"
    r"(?P<opts>(?:\s*\[[^\]]*\])*)"
    r"\s*\{(?P<keys>[^}]*)\}"
)

_SECTION_RE = re.compile(
    r"\\(?P<level>chapter|section|subsection|subsubsection)\*?\s*\{(?P<title>[^}]*)\}"
)

# Regions whose contents are not prose and must never be linted as claims.
_MATH_ENVS = ("equation", "align", "gather", "multline", "eqnarray", "displaymath", "math")
_VERBATIM_ENVS = ("verbatim", "lstlisting", "minted", "Verbatim", "tikzpicture")


def _mask_comments(text: str) -> str:
    """Blank every LaTeX comment — an unescaped ``%`` through end of line.

    Split out of :func:`_mask_regions` because two callers need *only* this stage: the
    unescaped-``%`` lint, which must see the raw text to find the offending character at
    all, and :func:`verbatim_spans`. Length and line structure are preserved, same as
    every other masking step.
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        if text[i] == "%" and (i == 0 or text[i - 1] != "\\"):
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):  # the range stops before the newline, so it survives
                out[k] = " "
            i = j
        i += 1
    return "".join(out)


def _mask_regions(text: str) -> str:
    """Replace comments, math, and verbatim regions with spaces of identical length.

    Masking rather than deleting is deliberate: every downstream offset stays valid
    against the original document, so ranges reported to the editor need no remapping.
    """
    out = list(_mask_comments(text))
    n = len(text)

    def blank(a: int, b: int) -> None:
        for i in range(max(0, a), min(n, b)):
            if out[i] != "\n":  # preserve line structure for the position index
                out[i] = " "

    masked = "".join(out)

    # 2. Display and inline math.
    for pattern in (r"\$\$.*?\$\$", r"\\\[.*?\\\]", r"(?<!\\)\$.*?(?<!\\)\$"):
        for m in re.finditer(pattern, masked, re.DOTALL):
            blank(m.start(), m.end())
        masked = "".join(out)

    # 3. Math / verbatim environments.
    for env in _MATH_ENVS + _VERBATIM_ENVS:
        pattern = re.compile(
            r"\\begin\{" + re.escape(env) + r"\*?\}.*?\\end\{" + re.escape(env) + r"\*?\}",
            re.DOTALL,
        )
        for m in pattern.finditer(masked):
            blank(m.start(), m.end())
        masked = "".join(out)

    return masked


#: Commands whose argument is a literal string, not prose. A ``%`` inside one is data —
#: percent-encoded URLs (``.../a%20b``) are the case that matters — so the unescaped-``%``
#: lint must not touch them even though the character genuinely does start a comment there.
_LITERAL_ARG_RE = re.compile(r"\\(?:url|href|path|nolinkurl|verb\*?)\s*\{[^}]*\}")


def find_literal_spans(text: str) -> List[Tuple[int, int]]:
    """Spans holding literal (non-prose) data: verbatim environments and URL arguments.

    Comments are masked first, mirroring :func:`_mask_regions`, so a ``\\begin{verbatim}``
    that is itself commented out does not open a region.
    """
    masked = _mask_comments(text)
    spans: List[Tuple[int, int]] = []

    for env in _VERBATIM_ENVS:
        pattern = re.compile(
            r"\\begin\{" + re.escape(env) + r"\*?\}.*?\\end\{" + re.escape(env) + r"\*?\}",
            re.DOTALL,
        )
        spans.extend((m.start(), m.end()) for m in pattern.finditer(masked))

    spans.extend((m.start(), m.end()) for m in _LITERAL_ARG_RE.finditer(masked))
    return sorted(spans)


def in_spans(spans: Sequence[Tuple[int, int]], offset: int) -> bool:
    """True if ``offset`` falls inside any span. Linear; span counts are small."""
    return any(start <= offset < end for start, end in spans)


# Abbreviations that end in a period but do not end a sentence.
_ABBREVIATIONS = frozenset(
    {
        "e.g", "i.e", "cf", "et al", "etc", "vs", "Fig", "fig", "Eq", "eq", "Sec", "sec",
        "Ref", "ref", "Tab", "tab", "approx", "resp", "Dr", "Prof", "Mr", "Mrs", "Ms",
        "St", "no", "No", "vol", "Vol", "pp", "ca",
    }
)

_SENTENCE_END_RE = re.compile(r"[.!?](?=[\s~]|$)")


def _split_sentences(masked: str, offset_base: int = 0) -> List[Tuple[str, int, int]]:
    """Split masked prose into (text, start, end) triples.

    Sentence segmentation in LaTeX is genuinely awkward — ``et al.`` and ``Fig.~3`` are
    not sentence ends, and neither is the period inside a masked equation. We use a
    conservative rule: a terminator ends a sentence unless the preceding token is a known
    abbreviation or a single capital letter (an initial, as in "R. Fisher").
    """
    results: List[Tuple[str, int, int]] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(masked):
        end = m.end()
        preceding = masked[start:end].rstrip(".!?").rstrip()
        last_token = preceding.rsplit(None, 1)[-1] if preceding.rsplit(None, 1) else ""
        last_token = last_token.strip("(){}[],;:")
        if last_token in _ABBREVIATIONS or (len(last_token) == 1 and last_token.isupper()):
            continue
        chunk = masked[start:end]
        if chunk.strip():
            results.append(_trim(masked, start, end, offset_base))
        start = end
    tail = masked[start:]
    if tail.strip():
        results.append(_trim(masked, start, len(masked), offset_base))
    return results


def _trim(masked: str, start: int, end: int, offset_base: int) -> Tuple[str, int, int]:
    """Shrink a span to its non-whitespace content.

    A sentence span naturally begins at the previous sentence's terminator, so it opens
    with the intervening newline. Left untrimmed, the editor would underline starting on
    the previous line — visually wrong and confusing to click.
    """
    s, e = start, end
    while s < e and masked[s].isspace():
        s += 1
    while e > s and masked[e - 1].isspace():
        e -= 1
    return (masked[s:e], offset_base + s, offset_base + e)


# --------------------------------------------------------------------------------------
# BibTeX parsing
# --------------------------------------------------------------------------------------

_BIB_ENTRY_START_RE = re.compile(r"@(?P<type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s}]+)\s*,")


def _match_brace(text: str, open_idx: int) -> int:
    """Return the index just past the ``}`` matching the ``{`` at ``open_idx``."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _parse_bib_fields(body: str) -> Dict[str, str]:
    """Parse ``name = {value}`` / ``name = "value"`` / ``name = bareword`` pairs."""
    fields: Dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        m = re.compile(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*").search(body, i)
        if not m:
            break
        name = m.group(1).lower()
        j = m.end()
        if j >= n:
            break
        if body[j] == "{":
            end = _match_brace(body, j)
            value = body[j + 1 : end - 1]
        elif body[j] == '"':
            end = body.find('"', j + 1)
            end = n if end == -1 else end + 1
            value = body[j + 1 : end - 1]
        else:
            end = j
            while end < n and body[end] not in ",\n":
                end += 1
            value = body[j:end]
        # BibTeX braces protect capitalisation ({BERT}) rather than carrying meaning.
        # Strip them all: the consumer is a citation verifier matching against index
        # titles, and "Nested {BRACES}" would never match "Nested BRACES".
        cleaned = value.replace("\n", " ").replace("{", "").replace("}", "")
        fields[name] = re.sub(r"\s+", " ", cleaned).strip()
        i = end
    return fields


def parse_bibtex(text: str) -> Dict[str, BibEntry]:
    """Parse a ``.bib`` file into ``{key: BibEntry}``.

    Later duplicates lose to earlier ones, mirroring BibTeX's own behaviour, and the
    duplicate is still detectable because callers can compare counts.
    """
    entries: Dict[str, BibEntry] = {}
    for m in _BIB_ENTRY_START_RE.finditer(text):
        entry_type = m.group("type").lower()
        if entry_type in ("comment", "preamble", "string"):
            continue
        key = m.group("key")
        brace_idx = text.find("{", m.start())
        end = _match_brace(text, brace_idx)
        body = text[m.end() : end - 1]
        if key not in entries:
            entries[key] = BibEntry(
                key=key,
                entry_type=entry_type,
                fields=_parse_bib_fields(body),
                start=m.start(),
                end=end,
            )
    return entries


# --------------------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------------------


@dataclass
class ResearchDocument:
    """A parsed paper: the ``.tex`` source plus its bibliography.

    Construct via :meth:`parse`. Instances are immutable snapshots tied to a document
    version; the engine discards and rebuilds one on every edit. Parsing is cheap
    (microseconds for a normal paper) — the expensive work is analysis, which is cached
    at a finer granularity than the document.
    """

    uri: str
    text: str
    version: int
    index: PositionIndex
    cite_refs: List[CiteKeyRef]
    sections: List[Section]
    sentences: List[Sentence]
    bib_entries: Dict[str, BibEntry]
    bib_uri: Optional[str] = None
    #: Offsets in :class:`BibEntry` index into the ``.bib`` text, not the ``.tex``, so
    #: they need their own line table. Mapping them through ``index`` yields plausible
    #: but entirely wrong line numbers — a bug worth naming, because it is silent.
    bib_index: Optional[PositionIndex] = None
    #: Verbatim environments and URL arguments, as offsets into :attr:`text`. Analyzers
    #: that read the *raw* source rather than the masked view need these to stay out of
    #: regions where LaTeX's normal escaping rules do not apply.
    literal_spans: List[Tuple[int, int]] = field(default_factory=list)

    @classmethod
    def parse(
        cls,
        uri: str,
        text: str,
        version: int = 0,
        bib_text: str = "",
        bib_uri: Optional[str] = None,
    ) -> ResearchDocument:
        index = PositionIndex(text)
        masked = _mask_regions(text)

        cite_refs: List[CiteKeyRef] = []
        for m in _CITE_RE.finditer(masked):
            cmd = m.group("cmd")
            keys_raw = m.group("keys")
            keys_start = m.start("keys")
            cursor = 0
            for part in keys_raw.split(","):
                stripped = part.strip()
                if stripped:
                    lead = len(part) - len(part.lstrip())
                    key_start = keys_start + cursor + lead
                    cite_refs.append(
                        CiteKeyRef(
                            key=stripped,
                            start=key_start,
                            end=key_start + len(stripped),
                            command=cmd,
                        )
                    )
                cursor += len(part) + 1

        sections: List[Section] = []
        section_matches = list(_SECTION_RE.finditer(masked))
        for i, m in enumerate(section_matches):
            end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(text)
            sections.append(
                Section(
                    title=m.group("title").strip(),
                    level=m.group("level"),
                    start=m.start(),
                    end=end,
                )
            )

        # Prose is everything after \begin{document} (or the whole file if absent), with
        # the sectioning commands themselves masked so titles don't become sentences.
        body_start = 0
        begin_doc = masked.find(r"\begin{document}")
        if begin_doc != -1:
            body_start = begin_doc + len(r"\begin{document}")
        prose = list(masked)
        for m in _SECTION_RE.finditer(masked):
            for i in range(m.start(), m.end()):
                if prose[i] != "\n":
                    prose[i] = " "
        prose_text = "".join(prose)[body_start:]

        sentences: List[Sentence] = []
        for chunk, s, e in _split_sentences(prose_text, offset_base=body_start):
            keys = [r.key for r in cite_refs if s <= r.start < e]
            sentences.append(
                Sentence(
                    text=_clean_prose(chunk),
                    start=s,
                    end=e,
                    cite_keys=keys,
                    section=_section_at(sections, s),
                )
            )

        return cls(
            uri=uri,
            text=text,
            version=version,
            index=index,
            cite_refs=cite_refs,
            sections=sections,
            sentences=sentences,
            bib_entries=parse_bibtex(bib_text),
            bib_uri=bib_uri,
            bib_index=PositionIndex(bib_text),
            literal_spans=find_literal_spans(text),
        )

    # -- convenience --------------------------------------------------------------------

    def cited_keys(self) -> List[str]:
        return sorted({r.key for r in self.cite_refs})

    def undefined_keys(self) -> List[CiteKeyRef]:
        return [r for r in self.cite_refs if r.key not in self.bib_entries]

    def unused_entries(self) -> List[BibEntry]:
        used = {r.key for r in self.cite_refs}
        return [e for e in self.bib_entries.values() if e.key not in used]

    def range_of(self, start: int, end: int) -> Range:
        return self.index.range(start, end)

    def bib_range_of(self, start: int, end: int) -> Range:
        """Map an offset span in the ``.bib`` source to a range in that file."""
        index = self.bib_index or PositionIndex("")
        return index.range(start, end)

    def cite_ref_at(self, offset: int) -> Optional[CiteKeyRef]:
        """The citation key under a cursor offset, if any — powers hover and code actions."""
        for ref in self.cite_refs:
            if ref.start <= offset <= ref.end:
                return ref
        return None


_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])*(?:\{[^}]*\})?")


def _clean_prose(chunk: str) -> str:
    """Strip residual LaTeX commands so claim analyzers see something close to English."""
    return re.sub(r"\s+", " ", _COMMAND_RE.sub(" ", chunk)).strip()


def _section_at(sections: Sequence[Section], offset: int) -> str:
    current = ""
    for s in sections:
        if s.start <= offset:
            current = s.title
        else:
            break
    return current
