"""The incremental analysis engine.

This is the ``clangd`` layer: it owns open documents, decides what to recompute when one
changes, and gets results back to the editor fast enough to feel live.

Three mechanisms do the work:

**Two-phase analysis.** Instant analyzers run synchronously on every edit and publish
immediately; network analyzers run on a background thread and publish a second, superset
round when they land. The author sees an undefined citation key the moment they type it,
and learns that the reference is fabricated a second later.

**Debouncing.** Network passes are delayed and coalesced, so holding down a key does not
queue fifty verification runs. Only the last edit in a burst reaches the network.

**Version guarding.** A background pass carries the document version it started from. If
the document has moved on by the time it finishes, its diagnostics are dropped rather
than published against text that no longer exists — the standard fix for the stale-result
race every language server has to solve.

Combined with the content-addressed cache, steady-state cost is near zero: edits that
don't touch the bibliography never hit the network at all.
"""
from __future__ import annotations

import inspect
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .analyzers import DEFAULT_ANALYZERS
from .analyzers.base import Analyzer
from .cache import ResultCache
from .diagnostics import AnalysisResult, Diagnostic
from .document import ResearchDocument

#: Milliseconds of quiet before a network pass fires. Long enough that normal typing
#: never triggers one; short enough that a pause feels like an immediate response.
DEFAULT_DEBOUNCE_MS = 700

PublishCallback = Callable[[str, List[Diagnostic], int], None]
"""``(uri, diagnostics, version)`` — how the engine hands results to a client."""


@dataclass
class EngineStats:
    instant_passes: int = 0
    network_passes: int = 0
    network_passes_dropped: int = 0
    cache_hits: int = 0
    total_instant_ms: float = 0.0
    total_network_ms: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "instant_passes": self.instant_passes,
            "network_passes": self.network_passes,
            "network_passes_dropped": self.network_passes_dropped,
            "avg_instant_ms": round(
                self.total_instant_ms / self.instant_passes, 2
            ) if self.instant_passes else 0.0,
            "avg_network_ms": round(
                self.total_network_ms / self.network_passes, 2
            ) if self.network_passes else 0.0,
        }


def _instantiate(classes, cache: ResultCache) -> List[Analyzer]:
    """Build the default analyzer set from :data:`DEFAULT_ANALYZERS`.

    Deriving the list from that constant rather than restating it here is what makes
    registering an analyzer a one-line change, as the contributor docs promise. Analyzers
    that accept a ``cache`` argument are handed the engine's shared cache so that every
    consumer of a cached verdict — the analyzer, the engine, hover — sees the same one.
    """
    out: List[Analyzer] = []
    for cls in classes:
        takes_cache = "cache" in inspect.signature(cls).parameters
        out.append(cls(cache=cache) if takes_cache else cls())
    return out


@dataclass
class _DocEntry:
    doc: ResearchDocument
    instant: List[Diagnostic] = field(default_factory=list)
    network: List[Diagnostic] = field(default_factory=list)
    timer: Optional[threading.Timer] = None


class AnalysisEngine:
    """Owns open documents and drives analyzers over them."""

    def __init__(
        self,
        analyzers: Optional[List[Analyzer]] = None,
        cache: Optional[ResultCache] = None,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        publish: Optional[PublishCallback] = None,
    ) -> None:
        self.cache = cache or ResultCache()
        self.debounce_ms = debounce_ms
        self.publish = publish
        self.stats = EngineStats()
        self._docs: Dict[str, _DocEntry] = {}
        self._lock = threading.RLock()
        self.analyzers: List[Analyzer] = (
            analyzers if analyzers is not None else _instantiate(DEFAULT_ANALYZERS, self.cache)
        )

    # -- document lifecycle -------------------------------------------------------------

    def open(
        self,
        uri: str,
        text: str,
        version: int = 0,
        bib_text: str = "",
        bib_uri: Optional[str] = None,
    ) -> List[Diagnostic]:
        return self.update(uri, text, version, bib_text, bib_uri)

    def update(
        self,
        uri: str,
        text: str,
        version: int,
        bib_text: str = "",
        bib_uri: Optional[str] = None,
    ) -> List[Diagnostic]:
        """Reparse, run the instant pass, and schedule the network pass.

        Returns the instant diagnostics synchronously — the caller can publish them
        without waiting for anything.
        """
        doc = ResearchDocument.parse(uri, text, version, bib_text, bib_uri)

        with self._lock:
            previous = self._docs.get(uri)
            if previous and previous.timer:
                previous.timer.cancel()
            # Carry the previous network diagnostics forward so the display doesn't flicker
            # empty between the instant pass and the next network pass landing.
            carried = previous.network if previous else []
            entry = _DocEntry(doc=doc, network=carried)
            self._docs[uri] = entry

        instant = self._run_pass(doc, network=False)
        with self._lock:
            entry.instant = instant

        self._schedule_network(uri, version)
        return self.diagnostics(uri)

    def close(self, uri: str) -> None:
        with self._lock:
            entry = self._docs.pop(uri, None)
            if entry and entry.timer:
                entry.timer.cancel()

    def document(self, uri: str) -> Optional[ResearchDocument]:
        with self._lock:
            entry = self._docs.get(uri)
            return entry.doc if entry else None

    def diagnostics(self, uri: str) -> List[Diagnostic]:
        """Current merged view: instant results plus the latest network results."""
        with self._lock:
            entry = self._docs.get(uri)
            if not entry:
                return []
            return list(entry.instant) + list(entry.network)

    # -- passes ---------------------------------------------------------------------------

    def _run_pass(self, doc: ResearchDocument, *, network: bool) -> List[Diagnostic]:
        started = time.perf_counter()
        results: List[AnalysisResult] = []
        out: List[Diagnostic] = []

        for analyzer in self.analyzers:
            if bool(getattr(analyzer, "is_network", False)) != network:
                continue
            t0 = time.perf_counter()
            try:
                diags = analyzer.run(doc)
                err = None
            except Exception as exc:  # one broken analyzer must not blank the whole pass
                diags, err = [], f"{type(exc).__name__}: {exc}"
            out.extend(diags)
            results.append(
                AnalysisResult(
                    analyzer=getattr(analyzer, "name", "?"),
                    diagnostics=diags,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    error=err,
                )
            )

        elapsed_ms = (time.perf_counter() - started) * 1000
        if network:
            self.stats.network_passes += 1
            self.stats.total_network_ms += elapsed_ms
        else:
            self.stats.instant_passes += 1
            self.stats.total_instant_ms += elapsed_ms
        self._last_results = results
        return out

    def _schedule_network(self, uri: str, version: int) -> None:
        """Arm (or re-arm) the debounced background verification pass."""
        if self.debounce_ms <= 0:
            self._network_pass(uri, version)
            return
        timer = threading.Timer(self.debounce_ms / 1000.0, self._network_pass, args=(uri, version))
        timer.daemon = True
        with self._lock:
            entry = self._docs.get(uri)
            if not entry:
                return
            entry.timer = timer
        timer.start()

    def _network_pass(self, uri: str, version: int) -> None:
        with self._lock:
            entry = self._docs.get(uri)
            if entry is None or entry.doc.version != version:
                self.stats.network_passes_dropped += 1
                return
            doc = entry.doc

        diags = self._run_pass(doc, network=True)

        with self._lock:
            entry = self._docs.get(uri)
            # The document may have changed while we were on the network. Publishing
            # ranges computed against stale text would underline the wrong words.
            if entry is None or entry.doc.version != version:
                self.stats.network_passes_dropped += 1
                return
            entry.network = diags
            merged = list(entry.instant) + diags

        self.cache.flush()
        if self.publish:
            self.publish(uri, merged, version)

    # -- synchronous helper ---------------------------------------------------------------

    def analyze_now(
        self,
        uri: str,
        text: str,
        bib_text: str = "",
        bib_uri: Optional[str] = None,
    ) -> List[Diagnostic]:
        """Run every analyzer, network included, and block until done.

        This is the CLI / CI entry point — the one you put in a pre-submission gate.
        """
        doc = ResearchDocument.parse(uri, text, 0, bib_text, bib_uri)
        with self._lock:
            self._docs[uri] = _DocEntry(doc=doc)
        instant = self._run_pass(doc, network=False)
        network = self._run_pass(doc, network=True)
        with self._lock:
            self._docs[uri].instant = instant
            self._docs[uri].network = network
        self.cache.flush()
        return instant + network

    def shutdown(self) -> None:
        with self._lock:
            for entry in self._docs.values():
                if entry.timer:
                    entry.timer.cancel()
            self._docs.clear()
        self.cache.flush()
