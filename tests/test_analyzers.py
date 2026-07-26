"""Analyzer behaviour: what gets flagged, and — more importantly — what does not."""
from __future__ import annotations

import pytest

from aurelius_ide.analyzers.citations import (
    IncompleteBibEntryAnalyzer,
    ScholarlyVerificationAnalyzer,
    UndefinedCitationAnalyzer,
    UnusedBibEntryAnalyzer,
)
from aurelius_ide.analyzers.claims import UncitedClaimAnalyzer
from aurelius_ide.cache import ResultCache
from aurelius_ide.diagnostics import Code, Severity
from aurelius_ide.verification import VerdictKind

from .conftest import BIB, StubVerifier, body, make_doc


def verifier_analyzer(verdict: str) -> ScholarlyVerificationAnalyzer:
    return ScholarlyVerificationAnalyzer(
        cache=ResultCache(persist=False), verifier=StubVerifier(verdict=verdict)
    )


# -- undefined citations -------------------------------------------------------------------


def test_undefined_citation_is_an_error():
    diags = UndefinedCitationAnalyzer().run(make_doc(r"\begin{document}\citep{nope}\end{document}"))
    assert len(diags) == 1
    assert diags[0].severity is Severity.ERROR
    assert diags[0].code == Code.UNDEFINED_CITATION


def test_undefined_citation_suggests_a_near_miss():
    doc = make_doc(r"\begin{document}\citep{smith202}\end{document}")
    assert UndefinedCitationAnalyzer().run(doc)[0].data["suggestion"] == "smith2020"


def test_no_suggestion_offered_for_a_wholly_unrelated_key():
    doc = make_doc(r"\begin{document}\citep{zzzz9999}\end{document}")
    assert UndefinedCitationAnalyzer().run(doc)[0].data["suggestion"] is None


def test_defined_citation_produces_no_diagnostic():
    doc = make_doc(r"\begin{document}\citep{smith2020}\end{document}")
    assert UndefinedCitationAnalyzer().run(doc) == []


# -- bibliography hygiene --------------------------------------------------------------------


def test_unused_bib_entry_is_reported_as_a_hint():
    doc = make_doc(r"\begin{document}\citep{smith2020}\citep{jones2021}\end{document}")
    diags = UnusedBibEntryAnalyzer().run(doc)
    assert [d.data["key"] for d in diags] == ["never_cited"]
    assert diags[0].severity is Severity.HINT


def test_nocite_counts_as_a_use():
    doc = make_doc(r"\begin{document}\nocite{never_cited}\end{document}")
    assert "never_cited" not in [d.data["key"] for d in UnusedBibEntryAnalyzer().run(doc)]


def test_incomplete_entry_reports_missing_required_fields():
    doc = make_doc(r"\begin{document}\citep{jones2021}\end{document}")
    diags = [d for d in IncompleteBibEntryAnalyzer().run(doc) if d.data["key"] == "jones2021"]
    assert diags and "booktitle" in diags[0].data["missing"]


def test_complete_entry_is_not_flagged():
    doc = make_doc(r"\begin{document}\citep{smith2020}\end{document}")
    assert not [d for d in IncompleteBibEntryAnalyzer().run(doc) if d.data["key"] == "smith2020"]


def test_bibliography_diagnostics_use_the_bib_position_index():
    doc = make_doc("\\begin{document}\n\\citep{smith2020}\n\\end{document}")
    diag = [d for d in UnusedBibEntryAnalyzer().run(doc) if d.data["key"] == "never_cited"][0]
    assert "never_cited" in BIB.splitlines()[diag.range.start.line]


# -- scholarly verification -------------------------------------------------------------------


def test_retracted_work_is_an_error():
    doc = make_doc(r"\begin{document}\citep{smith2020}\end{document}")
    diags = verifier_analyzer(VerdictKind.RETRACTED.value).run(doc)
    assert diags[0].severity is Severity.ERROR
    assert diags[0].code == Code.RETRACTED_CITATION


def test_missing_work_is_an_error():
    doc = make_doc(r"\begin{document}\citep{smith2020}\end{document}")
    diags = verifier_analyzer(VerdictKind.NOT_FOUND.value).run(doc)
    assert diags[0].code == Code.UNVERIFIED_CITATION


def test_verified_work_produces_no_diagnostic():
    doc = make_doc(r"\begin{document}\citep{smith2020}\end{document}")
    assert verifier_analyzer(VerdictKind.VERIFIED.value).run(doc) == []


def test_inconclusive_verification_is_silent():
    """A dropped connection must never render as 'this citation is fabricated'."""
    doc = make_doc(r"\begin{document}\citep{smith2020}\end{document}")
    assert verifier_analyzer(VerdictKind.ERROR.value).run(doc) == []


def test_one_bad_entry_cited_twice_flags_both_sites():
    """Every sentence resting on an unverifiable source is itself unsupported."""
    doc = make_doc(r"\begin{document}\citep{smith2020} and again \citep{smith2020}\end{document}")
    assert len(verifier_analyzer(VerdictKind.NOT_FOUND.value).run(doc)) == 2


def test_undefined_keys_are_not_sent_to_the_verifier():
    stub = StubVerifier()
    analyzer = ScholarlyVerificationAnalyzer(cache=ResultCache(persist=False), verifier=stub)
    analyzer.run(make_doc(r"\begin{document}\citep{does_not_exist}\end{document}"))
    assert stub.calls == 0


def test_uncited_entries_are_not_verified():
    """Never spend a network call on a reference the paper does not use."""
    stub = StubVerifier()
    analyzer = ScholarlyVerificationAnalyzer(cache=ResultCache(persist=False), verifier=stub)
    analyzer.run(make_doc(r"\begin{document}\citep{smith2020}\end{document}"))
    assert stub.calls == 1


def test_verifier_exceptions_do_not_propagate():
    class Exploding:
        name = "exploding"

        def verify(self, citation):
            raise RuntimeError("network on fire")

    analyzer = ScholarlyVerificationAnalyzer(cache=ResultCache(persist=False), verifier=Exploding())
    assert analyzer.run(make_doc(r"\begin{document}\citep{smith2020}\end{document}")) == []


# -- uncited claims -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        r"Recall improved by 45\% across every evaluated benchmark.",
        r"Throughput rose by 12\% under the same hardware budget.",
        "The correlation was strong at r = 0.71 across all cohorts.",
        "The effect was significant with p < 0.01 in every replication.",
        "The dataset contains 1,240,000 labelled training examples.",
        "Inference costs fell 3.2x relative to the published baseline.",
        "Studies show that this approach dominates the alternatives.",
        "It is widely known that transformers scale with data volume.",
        "Previous studies report the opposite relationship entirely.",
    ],
)
def test_uncited_empirical_claims_are_flagged(sentence):
    diags = UncitedClaimAnalyzer().run(make_doc(body(sentence)))
    assert diags, f"expected a diagnostic for: {sentence}"
    assert diags[0].code == Code.UNCITED_CLAIM


@pytest.mark.parametrize(
    "sentence",
    [
        r"Recall improved by 45\% across benchmarks \citep{smith2020}.",
        r"We find that recall improves by 45\% on the held-out split.",
        r"Our model achieves 93\% accuracy on the benchmark suite.",
        "As shown in Figure 3, the pipeline has four distinct stages.",
        "See Section 2 for the full derivation of the bound.",
        "This paper introduces a new estimator for the same quantity.",
        "We train for 3 epochs with a batch size of 64 throughout.",
        "Short claim.",
    ],
)
def test_legitimate_sentences_are_not_flagged(sentence):
    assert UncitedClaimAnalyzer().run(make_doc(body(sentence))) == []


def test_numbers_in_results_sections_are_not_treated_as_uncited_claims():
    tex = body("Latency fell to 12 ms at the same recall level.", section="Results")
    assert UncitedClaimAnalyzer().run(make_doc(tex)) == []


def test_appeal_to_literature_is_flagged_even_in_a_results_section():
    tex = body("Studies show this behaviour generalises to other domains.", section="Results")
    diags = UncitedClaimAnalyzer().run(make_doc(tex))
    assert diags and diags[0].data["reason"] == "appeal to prior work"


def test_unescaped_percent_comments_out_the_rest_of_the_line():
    """LaTeX treats a bare ``%`` as a comment, so the text after it is not prose — the
    compiled document genuinely does not contain it."""
    doc = make_doc(body("Recall improved by 45% across every benchmark."))
    assert "across every benchmark" not in " ".join(s.text for s in doc.sentences)
