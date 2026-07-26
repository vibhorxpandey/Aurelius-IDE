"""Uncited-claim analyzer.

A sentence asserting an empirical fact — a percentage, an effect size, a p-value, or an
appeal to what "studies show" — needs a source. This analyzer finds sentences that make
such a claim and carry no citation.

**False positives are the failure mode that kills a linter**, so the rules here are
deliberately conservative in three ways:

1. A sentence reporting the author's *own* results ("we find", "our model achieves",
   "Table 3 shows") is legitimately uncited — that is what a Results section is. These
   are excluded by first-person and self-reference markers.
2. Numbers that aren't claims are ignored: section cross-references, figure numbers,
   equation labels, page counts, and hyperparameter settings in Methods.
3. A citation anywhere in the sentence clears it. Attributing the sentence's *specific*
   number to the *right* source is a harder problem left to verification, not linting.

The result under-reports rather than over-reports. That is the correct trade: a linter
that cries wolf gets switched off, and a switched-off linter catches nothing.
"""
from __future__ import annotations

import re
from typing import List

from ..diagnostics import Code, Diagnostic, Severity
from ..document import ResearchDocument, Sentence
from .base import BaseAnalyzer

# Quantitative claim markers.
_STAT_PATTERNS = (
    # In LaTeX a literal percent is escaped (``12\%``); an unescaped one starts a
    # comment. Both forms must match or every percentage in a real paper is missed.
    re.compile(r"\b\d+(?:\.\d+)?\s*\\?%"),                    # 45%, 3.2 %, 12\%
    re.compile(r"\bp\s*[<>=]\s*0?\.\d+", re.IGNORECASE),      # p < 0.05
    re.compile(r"\b[rR]\s*=\s*-?0?\.\d+"),                    # r = 0.71
    re.compile(r"\b(?:N|n)\s*=\s*\d+"),                       # N = 240
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:x|×|-fold|fold)\b"),    # 3.2x, 5-fold
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),                    # 1,240,000
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:billion|million|trillion|bn|mn)\b", re.IGNORECASE),
    re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:kg|mg|km|cm|mm|ms|GB|MB|TB|GHz|MHz|kW|MW|°C|°F)\b"
    ),
)

# Appeals to literature with no citation attached — the classic unsourced assertion.
_ATTRIBUTION_RE = re.compile(
    r"\b(?:"
    r"studies\s+(?:show|suggest|indicate|find|have\s+shown)|"
    r"research\s+(?:shows|suggests|indicates|demonstrates|has\s+shown)|"
    r"(?:it\s+)?(?:is|has\s+been)\s+(?:widely\s+)?(?:known|shown|established|documented|reported)|"
    r"prior\s+work\s+(?:shows|has\s+shown|demonstrates)|"
    r"previous\s+studies|"
    r"the\s+literature\s+(?:shows|suggests|indicates)|"
    r"experts?\s+(?:agree|believe|argue)|"
    r"evidence\s+suggests"
    r")\b",
    re.IGNORECASE,
)

# The author's own work — legitimately uncited.
_SELF_REFERENCE_RE = re.compile(
    r"\b(?:"
    r"we\s+(?:find|show|report|observe|propose|present|introduce|achieve|obtain|measure|"
    r"train|evaluate|compare|use|apply|define|assume|conclude|demonstrate)|"
    r"our\s+(?:results?|model|method|approach|experiments?|analysis|data|system|"
    r"implementation|findings?|contribution)|"
    r"this\s+(?:paper|work|study|section|article)|"
    r"the\s+(?:proposed|present)\s+(?:method|model|approach|work)|"
    r"as\s+shown\s+in\s+(?:table|figure|fig|section)|"
    r"table\s+\d|figure\s+\d|fig\.\s*\d|algorithm\s+\d"
    r")\b",
    re.IGNORECASE,
)

# Numeric contexts that are not empirical claims.
_NON_CLAIM_CONTEXT_RE = re.compile(
    r"\b(?:section|figure|fig|table|equation|eq|appendix|algorithm|chapter|step|"
    r"listing|line|page|version|epoch|layer|seed)\s*\.?\s*\d",
    re.IGNORECASE,
)

# Sections where uncited numbers are expected rather than suspicious.
_SELF_REPORTING_SECTIONS = re.compile(
    r"\b(?:result|experiment|evaluation|method|methodolog|implementation|setup|"
    r"ablation|discussion|conclusion|acknowledg)", re.IGNORECASE
)

_MIN_SENTENCE_CHARS = 25


class UncitedClaimAnalyzer(BaseAnalyzer):
    """Flag empirical assertions with no supporting citation."""

    name = "uncited_claim"
    is_network = False

    def run(self, doc: ResearchDocument) -> List[Diagnostic]:
        out: List[Diagnostic] = []
        for sentence in doc.sentences:
            reason = self._claim_reason(sentence)
            if reason is None:
                continue
            out.append(
                Diagnostic(
                    range=doc.range_of(sentence.start, sentence.end),
                    message=(
                        f"Uncited {reason}. Every empirical claim should carry a "
                        f"verifiable source."
                    ),
                    severity=Severity.WARNING,
                    code=Code.UNCITED_CLAIM,
                    data={"text": sentence.text[:300], "reason": reason},
                )
            )
        return out

    # -- rules --------------------------------------------------------------------------

    def _claim_reason(self, sentence: Sentence) -> str | None:
        text = sentence.text
        if len(text) < _MIN_SENTENCE_CHARS or sentence.cite_keys:
            return None
        if _SELF_REFERENCE_RE.search(text):
            return None

        # An appeal to the literature is unsourced regardless of which section it's in —
        # "studies show" in a Results section is still an unsourced claim.
        if _ATTRIBUTION_RE.search(text):
            return "appeal to prior work"

        if _SELF_REPORTING_SECTIONS.search(sentence.section):
            return None

        stripped = _NON_CLAIM_CONTEXT_RE.sub(" ", text)
        for pattern in _STAT_PATTERNS:
            if pattern.search(stripped):
                return "quantitative claim"
        return None
