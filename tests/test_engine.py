"""Engine scheduling, caching, and the verification boundary."""
from __future__ import annotations

import time

from aurelius_ide.analyzers.citations import (
    ScholarlyVerificationAnalyzer,
    UndefinedCitationAnalyzer,
    UnusedBibEntryAnalyzer,
)
from aurelius_ide.cache import ResultCache
from aurelius_ide.diagnostics import Code
from aurelius_ide.engine import AnalysisEngine
from aurelius_ide.verification import (
    INCONCLUSIVE,
    AureliusVerifier,
    NullVerifier,
    VerdictKind,
    Verifier,
    get_default_verifier,
    set_default_verifier,
)

from .conftest import BIB, StubVerifier

TEX = r"\begin{document}\citep{smith2020}\end{document}"


def stub_analyzer(verdict=VerdictKind.NOT_FOUND.value, delay=0.0):
    stub = StubVerifier(verdict=verdict, delay=delay)
    analyzer = ScholarlyVerificationAnalyzer(cache=ResultCache(persist=False), verifier=stub)
    return analyzer, stub


# -- cache ----------------------------------------------------------------------------------


def test_cache_returns_stored_values_and_misses_unknown_keys():
    c = ResultCache(persist=False)
    c.set("a", "h1", {"verdict": "verified"})
    assert c.get("a", "h1") == {"verdict": "verified"}
    assert c.get("a", "h2") is None
    assert c.get("b", "h1") is None


def test_cache_expires_entries_past_their_ttl():
    c = ResultCache(ttl_seconds=0, persist=False)
    c.set("a", "h1", 1)
    time.sleep(0.01)
    assert c.get("a", "h1") is None


def test_cache_invalidate_removes_a_single_entry():
    c = ResultCache(persist=False)
    c.set("a", "h1", 1)
    c.invalidate("a", "h1")
    assert c.get("a", "h1") is None


def test_cache_persists_across_instances(tmp_path):
    path = tmp_path / "cache.json"
    a = ResultCache(path=path)
    a.set("analyzer", "hash", {"verdict": "verified"})
    a.flush()
    assert ResultCache(path=path).get("analyzer", "hash") == {"verdict": "verified"}


def test_cache_survives_a_corrupt_file(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json", encoding="utf-8")
    assert ResultCache(path=path).stats()["entries"] == 0


# -- verification boundary ---------------------------------------------------------------------


def test_null_verifier_reports_an_inconclusive_verdict():
    result = NullVerifier().verify("anything")
    assert result["verdict"] in {v.value for v in INCONCLUSIVE}


def test_stub_satisfies_the_verifier_protocol():
    assert isinstance(StubVerifier(), Verifier)
    assert isinstance(NullVerifier(), Verifier)


def test_default_verifier_falls_back_when_the_backend_is_absent():
    set_default_verifier(None)
    assert get_default_verifier().name in {"aurelius", "null"}


def test_default_verifier_can_be_overridden():
    stub = StubVerifier()
    set_default_verifier(stub)
    try:
        assert get_default_verifier() is stub
    finally:
        set_default_verifier(None)


def test_aurelius_verifier_reports_absence_of_backend_without_raising():
    v = AureliusVerifier()
    v._verify_citation = None
    if not v.available:
        assert v.verify("x")["verdict"] == VerdictKind.ERROR.value


def test_offline_not_found_is_downgraded_to_inconclusive():
    """The bug this exists to prevent: an unreachable index reporting every reference in
    the bibliography as fabricated."""
    v = AureliusVerifier()
    v._verify_citation = lambda citation, max_results=5: {
        "ok": True,
        "verdict": VerdictKind.NOT_FOUND.value,
    }
    v._offline = True  # simulate a failed connectivity probe
    assert v.verify("Some Paper (2020)")["verdict"] == VerdictKind.ERROR.value


def test_online_not_found_is_preserved_as_a_finding():
    v = AureliusVerifier()
    v._verify_citation = lambda citation, max_results=5: {
        "ok": True,
        "verdict": VerdictKind.NOT_FOUND.value,
        "notes": "",
    }
    v._offline = False
    assert v.verify("Some Paper (2020)")["verdict"] == VerdictKind.NOT_FOUND.value


# -- engine -------------------------------------------------------------------------------------


def test_engine_returns_instant_diagnostics_synchronously():
    eng = AnalysisEngine(analyzers=[UndefinedCitationAnalyzer()], debounce_ms=0)
    diags = eng.update("u", r"\begin{document}\citep{nope}\end{document}", 1, BIB)
    assert [d.code for d in diags] == [Code.UNDEFINED_CITATION]
    eng.shutdown()


def test_engine_merges_network_diagnostics_after_the_background_pass():
    analyzer, _ = stub_analyzer()
    eng = AnalysisEngine(analyzers=[UndefinedCitationAnalyzer(), analyzer], debounce_ms=10)
    eng.update("u", TEX, 1, BIB)
    time.sleep(0.25)
    assert Code.UNVERIFIED_CITATION in {d.code for d in eng.diagnostics("u")}
    eng.shutdown()


def test_engine_drops_network_results_for_stale_document_versions():
    """The stale-result race: a slow verification must not publish against text that has
    since changed, or diagnostics land on the wrong ranges."""
    analyzer, _ = stub_analyzer(delay=0.15)
    published = []
    eng = AnalysisEngine(
        analyzers=[analyzer],
        debounce_ms=1,
        publish=lambda uri, diags, version: published.append(version),
    )
    eng.update("u", TEX, 1, BIB)
    time.sleep(0.02)
    eng.update("u", TEX + " More prose here.", 2, BIB)
    time.sleep(0.45)
    assert 1 not in published, "a stale version was published"
    assert eng.stats.network_passes_dropped >= 1
    eng.shutdown()


def test_editing_prose_does_not_re_verify_the_bibliography():
    """The property that makes live analysis affordable."""
    analyzer, stub = stub_analyzer(verdict=VerdictKind.VERIFIED.value)
    eng = AnalysisEngine(analyzers=[analyzer], debounce_ms=0)
    eng.analyze_now("u", TEX, BIB)
    first = stub.calls
    eng.analyze_now("u", TEX + " Additional prose citing nothing new.", BIB)
    assert stub.calls == first
    eng.shutdown()


def test_editing_a_bib_entry_does_re_verify_it():
    analyzer, stub = stub_analyzer(verdict=VerdictKind.VERIFIED.value)
    eng = AnalysisEngine(analyzers=[analyzer], debounce_ms=0)
    eng.analyze_now("u", TEX, BIB)
    first = stub.calls
    eng.analyze_now("u", TEX, BIB.replace("year = {2020}", "year = {2021}"))
    assert stub.calls == first + 1
    eng.shutdown()


def test_engine_reports_live_progress_events_during_the_network_pass():
    analyzer, _ = stub_analyzer(verdict=VerdictKind.VERIFIED.value)
    events: list[tuple[str, str, str, str]] = []
    eng = AnalysisEngine(
        analyzers=[analyzer],
        debounce_ms=10,
        on_progress=lambda uri, key, source, status: events.append((uri, key, source, status)),
    )
    eng.update("u", TEX, 1, BIB)
    time.sleep(0.25)
    assert events == [
        ("u", "smith2020", "stub_source", "checking"),
        ("u", "smith2020", "stub_source", "hit"),
    ]
    eng.shutdown()


def test_engine_drops_stale_progress_outcomes_for_superseded_document_versions():
    """Same stale-result race as diagnostics: the *outcome* of a superseded pass must not
    surface. A "checking" ping that fired before the edit is accurate for the moment it
    fired, so only one terminal (hit/miss) event — the fresh pass's — should survive."""
    analyzer, _ = stub_analyzer(delay=0.15)
    events: list[tuple[str, str, str, str]] = []
    eng = AnalysisEngine(
        analyzers=[analyzer],
        debounce_ms=1,
        on_progress=lambda uri, key, source, status: events.append((uri, key, source, status)),
    )
    eng.update("u", TEX, 1, BIB)
    time.sleep(0.02)
    eng.update("u", TEX + " More prose here.", 2, BIB)
    time.sleep(0.45)
    terminal = [e for e in events if e[3] in ("hit", "miss")]
    assert len(terminal) == 1, "only the fresh pass's outcome should survive"
    eng.shutdown()


def test_no_on_progress_configured_does_not_crash_the_network_pass():
    analyzer, _ = stub_analyzer(verdict=VerdictKind.VERIFIED.value)
    eng = AnalysisEngine(analyzers=[analyzer], debounce_ms=0)
    diags = eng.analyze_now("u", TEX, BIB)
    assert diags == []
    eng.shutdown()


def test_analyze_now_runs_both_phases_synchronously():
    analyzer, _ = stub_analyzer(verdict=VerdictKind.RETRACTED.value)
    eng = AnalysisEngine(analyzers=[UndefinedCitationAnalyzer(), analyzer], debounce_ms=0)
    diags = eng.analyze_now("u", r"\begin{document}\citep{smith2020}\citep{bad}\end{document}", BIB)
    codes = {d.code for d in diags}
    assert Code.UNDEFINED_CITATION in codes and Code.RETRACTED_CITATION in codes
    eng.shutdown()


def test_a_failing_analyzer_does_not_blank_the_whole_pass():
    class Exploding(UndefinedCitationAnalyzer):
        name = "exploding"

        def run(self, doc):
            raise RuntimeError("boom")

    eng = AnalysisEngine(analyzers=[Exploding(), UnusedBibEntryAnalyzer()], debounce_ms=0)
    diags = eng.update("u", TEX, 1, BIB)
    assert any(d.code == Code.UNUSED_BIB_ENTRY for d in diags)
    eng.shutdown()


def test_closing_a_document_clears_its_diagnostics():
    eng = AnalysisEngine(analyzers=[UndefinedCitationAnalyzer()], debounce_ms=0)
    eng.update("u", r"\begin{document}\citep{nope}\end{document}", 1, BIB)
    eng.close("u")
    assert eng.diagnostics("u") == []
    assert eng.document("u") is None
    eng.shutdown()


def test_debounce_coalesces_a_burst_of_edits():
    analyzer, stub = stub_analyzer(verdict=VerdictKind.VERIFIED.value)
    eng = AnalysisEngine(analyzers=[analyzer], debounce_ms=60)
    for version in range(1, 6):
        eng.update("u", TEX + " " * version, version, BIB)
        time.sleep(0.005)
    time.sleep(0.3)
    assert eng.stats.network_passes <= 2, "burst was not coalesced"
    eng.shutdown()


def test_stats_report_pass_counts_and_timings():
    eng = AnalysisEngine(analyzers=[UndefinedCitationAnalyzer()], debounce_ms=0)
    eng.update("u", TEX, 1, BIB)
    stats = eng.stats.as_dict()
    assert stats["instant_passes"] >= 1
    assert stats["avg_instant_ms"] >= 0
    eng.shutdown()
