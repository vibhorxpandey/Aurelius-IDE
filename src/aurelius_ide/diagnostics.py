"""Diagnostic types.

Deliberately mirrors the LSP ``Diagnostic`` shape without importing an LSP library, so
the engine stays dependency-free and the same objects can be rendered by a CLI, a web
UI, or the language server.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from .document import Range


class Severity(IntEnum):
    """Same numbering as LSP's DiagnosticSeverity."""

    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class Code:
    """Stable diagnostic codes.

    These are part of the public contract: editor config, CI gates, and code actions all
    key off them, so renaming one is a breaking change.
    """

    UNDEFINED_CITATION = "AUR001"
    UNVERIFIED_CITATION = "AUR002"
    RETRACTED_CITATION = "AUR003"
    AUTHOR_MISMATCH = "AUR004"
    UNUSED_BIB_ENTRY = "AUR005"
    UNCITED_CLAIM = "AUR006"
    INCOMPLETE_BIB_ENTRY = "AUR007"
    UNESCAPED_PERCENT = "AUR008"
    CITATION_BINDING = "AUR009"
    COMPILE_ERROR = "AUR010"
    COMPILE_WARNING = "AUR011"


@dataclass
class Diagnostic:
    """One finding, anchored to a range in the document."""

    range: Range
    message: str
    severity: Severity = Severity.WARNING
    code: str = ""
    source: str = "aurelius"
    # Free-form payload consumed by code actions (e.g. a corrected citation string, the
    # BibTeX for a matched work). Never rendered directly to the user.
    data: dict[str, Any] = field(default_factory=dict)

    def to_lsp(self) -> dict[str, Any]:
        return {
            "range": {
                "start": {"line": self.range.start.line, "character": self.range.start.character},
                "end": {"line": self.range.end.line, "character": self.range.end.character},
            },
            "message": self.message,
            "severity": int(self.severity),
            "code": self.code,
            "source": self.source,
            "data": self.data,
        }


@dataclass
class AnalysisResult:
    """What one analyzer produced for one document version."""

    analyzer: str
    diagnostics: list
    from_cache: bool = False
    duration_ms: float = 0.0
    error: str | None = None
