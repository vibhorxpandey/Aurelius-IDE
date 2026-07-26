"""Analyzer protocol.

An analyzer is a pure function from a document to a list of diagnostics. The engine cares
about exactly one extra property: whether it touches the network.

That split drives the whole responsiveness story. **Instant** analyzers (undefined keys,
unused entries, uncited claims) are pure string work over an already-parsed document —
microseconds — so they run synchronously on every keystroke. **Network** analyzers
(scholarly verification) run on a debounced background thread and publish a second,
richer round of diagnostics when they land.

The user therefore sees structural errors immediately and evidential errors a moment
later, which is exactly how a code IDE separates parse errors from type errors.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..diagnostics import Diagnostic
from ..document import ResearchDocument


@runtime_checkable
class Analyzer(Protocol):
    """Structural contract for all analyzers."""

    name: str
    #: True if ``run`` performs I/O and must not block the editor's main loop.
    is_network: bool

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:
        ...


class BaseAnalyzer:
    """Convenience base with sane defaults."""

    name: str = "base"
    is_network: bool = False

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:  # pragma: no cover - abstract
        raise NotImplementedError
