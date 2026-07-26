"""LaTeX source lints — mistakes in the markup rather than in the scholarship.

Right now this is one check, and it is the most costly typo in LaTeX: an unescaped ``%``.

``We observed a 45% improvement in recall.`` compiles cleanly, produces no warning, and
silently renders as ``We observed a 45``. The rest of the sentence is gone. Authors find
out from a reviewer, or never. Nothing in the toolchain flags it, because from LaTeX's
point of view a comment is exactly what you asked for.

Detecting it needs the *raw* text. Every other analyzer reads the masked view, where
comments have already been blanked away — by the time masking is done, the evidence is
gone. So this module works against ``doc.text`` and re-derives comment boundaries itself.

**Precision matters more than recall here**, because deliberate comments vastly outnumber
accidental ones and flagging even a few would make the check unusable. Three restrictions
keep it quiet:

1. Only a ``%`` *immediately* preceded by a digit is reported. ``45%`` is a literal
   percent sign essentially every time; ``x = 5 % explain`` is a real comment, and
   requiring adjacency separates them without needing to understand the line.
2. Only the first unescaped ``%`` on a line can be flagged. A later one is already inside
   a comment, where a bare ``%`` means nothing.
3. Verbatim environments and URL-bearing arguments are skipped entirely — ``%20`` in a
   percent-encoded URL is a digit followed by ``%`` and is entirely correct.

The cost of the trade is that ``45 %`` with a space goes unreported. That is the right
direction to miss in: the fix is one character and the author can still see it, whereas a
linter that flags real comments gets switched off within a day.
"""
from __future__ import annotations

import re
from typing import List

from ..diagnostics import Code, Diagnostic, Severity
from ..document import ResearchDocument, in_spans
from .base import BaseAnalyzer

#: A digit, then a ``%`` with nothing in between. No backslash exclusion is needed: in the
#: correctly-escaped ``45\%`` the character preceding ``%`` is the backslash rather than
#: the digit, so the lookbehind already declines to match the form we ask authors to write.
_BARE_PERCENT_RE = re.compile(r"(?<=\d)%")


class UnescapedPercentAnalyzer(BaseAnalyzer):
    """Flag a literal ``%`` that silently comments out the rest of its line."""

    name = "unescaped_percent"
    is_network = False

    def run(self, doc: ResearchDocument) -> List[Diagnostic]:
        text = doc.text
        out: List[Diagnostic] = []

        for line_start, line in _lines(text):
            comment_at = _first_comment_offset(line)
            for m in _BARE_PERCENT_RE.finditer(line):
                at = m.start()
                # Anything at or past the line's first unescaped % is inside a comment.
                if comment_at is not None and at > comment_at:
                    break
                absolute = line_start + at
                if in_spans(doc.literal_spans, absolute):
                    continue
                out.append(
                    Diagnostic(
                        range=doc.range_of(absolute, absolute + 1),
                        message=(
                            "Unescaped '%' after a digit — LaTeX reads this as a comment "
                            "and drops the rest of the line. Write '\\%' for a literal "
                            "percent sign."
                        ),
                        severity=Severity.WARNING,
                        code=Code.UNESCAPED_PERCENT,
                        data={
                            "replacement": "\\%",
                            "dropped": line[at + 1 :].strip()[:120],
                        },
                    )
                )
        return out


def _lines(text: str):
    """Yield ``(absolute_start_offset, line_without_newline)`` for each line."""
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        yield offset, stripped
        offset += len(line)


def _first_comment_offset(line: str):
    """Offset of the first unescaped ``%`` in ``line``, or ``None``.

    A ``%`` preceded by a backslash is escaped — except when that backslash is itself
    escaped (``\\\\%`` is a line break followed by a genuine comment), so the run of
    preceding backslashes has to be counted rather than merely peeked at.
    """
    for i, ch in enumerate(line):
        if ch != "%":
            continue
        backslashes = 0
        j = i - 1
        while j >= 0 and line[j] == "\\":
            backslashes += 1
            j -= 1
        if backslashes % 2 == 0:
            return i
    return None
