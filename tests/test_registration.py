"""Analyzer registration is real, not decorative.

``DEFAULT_ANALYZERS`` is what the contributor docs tell you to edit when adding a check.
For a while it was only a re-export list while the engine kept a hardcoded copy, so
following the documented step registered nothing. These tests pin the two together: if
they drift apart again, the instant-pass assertions below stop seeing the new codes.
"""
from __future__ import annotations

from aurelius_ide.analyzers import DEFAULT_ANALYZERS
from aurelius_ide.cache import ResultCache
from aurelius_ide.diagnostics import Code
from aurelius_ide.engine import AnalysisEngine

from .conftest import BIB

PAPER = r"""\begin{document}
\section{Introduction}
Adoption grew by 45% across both corpora.
Smith et al.~\cite{jones2021} report the same effect.
\end{document}
"""


def engine() -> AnalysisEngine:
    # debounce_ms=0 would fire the network pass inline; a large value keeps this test to
    # the instant phase, which is where both new analyzers live.
    return AnalysisEngine(cache=ResultCache(persist=False), debounce_ms=100_000)


def test_engine_instantiates_every_registered_analyzer():
    names = {a.name for a in engine().analyzers}
    assert len(names) == len(DEFAULT_ANALYZERS)
    assert "unescaped_percent" in names
    assert "citation_binding" in names


def test_registered_analyzers_reach_the_instant_pass():
    diags = engine().update("file:///p.tex", PAPER, 1, BIB, "file:///p.bib")
    codes = {d.code for d in diags}
    assert Code.UNESCAPED_PERCENT in codes
    assert Code.CITATION_BINDING in codes


def test_shared_cache_reaches_the_analyzers_that_accept_one():
    cache = ResultCache(persist=False)
    eng = AnalysisEngine(cache=cache, debounce_ms=100_000)
    caches = [a.cache for a in eng.analyzers if hasattr(a, "cache")]
    assert caches, "no analyzer accepted the engine's cache"
    assert all(c is cache for c in caches)


def test_explicit_analyzer_list_still_overrides_the_default():
    eng = AnalysisEngine(analyzers=[], cache=ResultCache(persist=False), debounce_ms=100_000)
    assert eng.analyzers == []
