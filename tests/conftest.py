"""Shared fixtures.

``StubVerifier`` implements the :class:`~aurelius_ide.verification.Verifier` protocol so
engine and analyzer tests never touch the network. It overrides the *transport*, not the
caching layer, which is what makes the cache independently testable.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from aurelius_ide.document import ResearchDocument
from aurelius_ide.verification import VerdictKind

FIXTURES = Path(__file__).parent / "fixtures"

BIB = """
@article{smith2020,
  author = {Smith, Jane and Doe, John},
  title = {A Study of Things},
  journal = {Journal of Things},
  year = {2020},
  doi = {10.1234/things}
}
@inproceedings{jones2021,
  author = {Jones, Alice},
  title = {Nested {BRACES} in a Title},
  year = {2021}
}
@article{never_cited,
  author = {Ghost, A.},
  title = {Unread},
  journal = {Void},
  year = {1999}
}
"""


def make_doc(tex: str, bib: str = BIB) -> ResearchDocument:
    return ResearchDocument.parse("file:///p.tex", tex, 1, bib, "file:///p.bib")


def body(text: str, section: str = "Introduction") -> str:
    return f"\\begin{{document}}\n\\section{{{section}}}\n{text}\n\\end{{document}}"


class StubVerifier:
    """Hermetic verifier with a configurable verdict and latency."""

    name = "stub"

    def __init__(self, verdict: str = VerdictKind.NOT_FOUND.value, delay: float = 0.0):
        self.verdict = verdict
        self.delay = delay
        self.calls = 0

    def verify(self, citation: str, on_step=None) -> dict[str, Any]:
        self.calls += 1
        if on_step:
            on_step("stub_source", "checking")
        if self.delay:
            time.sleep(self.delay)
        if on_step:
            on_step("stub_source", "miss" if self.verdict == VerdictKind.ERROR.value else "hit")
        return {
            "ok": self.verdict != VerdictKind.ERROR.value,
            "verdict": self.verdict,
            "confidence": "high",
            "notes": "stub",
            "author_match": True,
            "matched_work": {"title": "T"},
            "bibtex": "@article{stub, title={T}}",
        }


@pytest.fixture
def paper_tex() -> str:
    return (FIXTURES / "paper.tex").read_text(encoding="utf-8")


@pytest.fixture
def paper_bib() -> str:
    return (FIXTURES / "references.bib").read_text(encoding="utf-8")
