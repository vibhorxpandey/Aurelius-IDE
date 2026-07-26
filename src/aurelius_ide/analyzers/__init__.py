"""Analyzers: pure functions from a parsed document to diagnostics."""
from .base import Analyzer, BaseAnalyzer
from .binding import CitationBindingAnalyzer
from .citations import (
    IncompleteBibEntryAnalyzer,
    ScholarlyVerificationAnalyzer,
    UndefinedCitationAnalyzer,
    UnusedBibEntryAnalyzer,
)
from .claims import UncitedClaimAnalyzer
from .syntax import UnescapedPercentAnalyzer

#: Instantiated in this order by :class:`~aurelius_ide.engine.AnalysisEngine`.
DEFAULT_ANALYZERS = (
    UndefinedCitationAnalyzer,
    UnusedBibEntryAnalyzer,
    IncompleteBibEntryAnalyzer,
    UncitedClaimAnalyzer,
    UnescapedPercentAnalyzer,
    CitationBindingAnalyzer,
    ScholarlyVerificationAnalyzer,
)

__all__ = [
    "Analyzer",
    "BaseAnalyzer",
    "UndefinedCitationAnalyzer",
    "UnusedBibEntryAnalyzer",
    "IncompleteBibEntryAnalyzer",
    "ScholarlyVerificationAnalyzer",
    "UncitedClaimAnalyzer",
    "UnescapedPercentAnalyzer",
    "CitationBindingAnalyzer",
    "DEFAULT_ANALYZERS",
]
