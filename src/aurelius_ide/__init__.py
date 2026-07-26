"""Aurelius IDE — live research-integrity analysis for LaTeX papers.

A language server that treats a paper like source code: undefined citation keys are
unresolved symbols, unverifiable references are type errors, and uncited empirical claims
are lint warnings.

The analysis engine is pure standard library. Scholarly verification is a swappable
backend (see :mod:`aurelius_ide.verification`); the LSP transport needs ``pygls`` and
installs via the ``lsp`` extra.

    from aurelius_ide import AnalysisEngine

    engine = AnalysisEngine()
    for d in engine.analyze_now("file:///paper.tex", tex_source, bib_text=bib_source):
        print(d.severity.name, d.code, d.message)
"""
from .cache import ResultCache
from .compiling import CompileGate, CompileRunner, DockerRunner, SubprocessRunner, default_gate
from .diagnostics import Code, Diagnostic, Severity
from .document import BibEntry, CiteKeyRef, Position, Range, ResearchDocument
from .engine import AnalysisEngine
from .verification import (
    AureliusVerifier,
    NullSearcher,
    NullVerifier,
    OpenAlexSearcher,
    Searcher,
    VerdictKind,
    Verifier,
    get_default_searcher,
    get_default_verifier,
    set_default_searcher,
    set_default_verifier,
    to_bibtex,
)

#: The canonical version for the whole project. `pyproject.toml` reads this via hatchling,
#: `lsp.py` imports it, and `scripts/sync_version.py` propagates it to the extension
#: manifest and the release manifest. Change it here and nowhere else.
__version__ = "0.3.0"

__all__ = [
    "__version__",
    "AnalysisEngine",
    "ResearchDocument",
    "Diagnostic",
    "Severity",
    "Code",
    "ResultCache",
    "BibEntry",
    "CiteKeyRef",
    "Position",
    "Range",
    "Verifier",
    "VerdictKind",
    "AureliusVerifier",
    "NullVerifier",
    "get_default_verifier",
    "set_default_verifier",
    "CompileGate",
    "CompileRunner",
    "SubprocessRunner",
    "DockerRunner",
    "default_gate",
    "Searcher",
    "OpenAlexSearcher",
    "NullSearcher",
    "get_default_searcher",
    "set_default_searcher",
    "to_bibtex",
]
