"""Claim-to-source binding (AUR009).

This check reads prose and guesses at surnames, which is exactly the kind of analyzer
that turns into a nuisance. The negative cases below are the specification: every
capitalised word that precedes a citation without naming anyone, every legitimate spelling
variation between prose and BibTeX, and every construct where disagreement is not
decidable must stay silent.
"""
from __future__ import annotations

from aurelius_ide.analyzers.binding import CitationBindingAnalyzer, _surnames
from aurelius_ide.diagnostics import Code, Severity

from .conftest import body, make_doc

BIB = """
@article{smith2019,
  author = {Smith, Jane and Roe, Richard},
  title = {A Study}, journal = {J}, year = {2019}
}
@article{jones2021,
  author = {Jones, Alice},
  title = {Another Study}, journal = {J}, year = {2021}
}
@article{vandijk2020,
  author = {van Dijk, Piet},
  title = {A Third}, journal = {J}, year = {2020}
}
@article{muller2018,
  author = {M\\"uller, Hans},
  title = {A Fourth}, journal = {J}, year = {2018}
}
@article{noauthor2022,
  title = {Anonymous}, journal = {J}, year = {2022}
}
"""


def run(tex: str):
    return CitationBindingAnalyzer().run(make_doc(body(tex), BIB))


# -- must flag ---------------------------------------------------------------------------


def test_flags_wrong_author_with_et_al():
    diags = run("Smith et al.~\\cite{jones2021} showed the effect persists.")
    assert len(diags) == 1
    assert diags[0].code == Code.CITATION_BINDING
    assert diags[0].severity is Severity.WARNING
    assert "no author named Smith" in diags[0].message


def test_flags_wrong_author_with_parenthetical_year():
    diags = run("Smith (2019) \\cite{jones2021} showed the effect persists.")
    assert len(diags) == 1
    assert diags[0].data["key"] == "jones2021"


def test_suggests_the_entry_that_matches_the_prose():
    diags = run("Smith et al.~\\cite{jones2021} showed the effect persists.")
    assert diags[0].data["suggestion"] == "smith2019"
    assert "Did you mean 'smith2019'?" in diags[0].message


def test_flags_year_mismatch_even_when_the_author_is_right():
    diags = run("Jones et al. (2019) \\cite{jones2021} showed the effect.")
    assert len(diags) == 1
    assert "the year is 2021, not 2019" in diags[0].message


def test_range_spans_the_narrative_citation():
    tex = body("Smith et al.~\\cite{jones2021} showed the effect.")
    doc = make_doc(tex, BIB)
    diag = CitationBindingAnalyzer().run(doc)[0]
    covered = doc.text[
        _offset(doc, diag.range.start.line, diag.range.start.character):
        _offset(doc, diag.range.end.line, diag.range.end.character)
    ]
    assert covered.startswith("Smith")
    assert covered.endswith("}")


def _offset(doc, line, character):
    offset = 0
    for i, content in enumerate(doc.text.splitlines(keepends=True)):
        if i == line:
            return offset + character
        offset += len(content)
    return offset


# -- must not flag -----------------------------------------------------------------------


def test_correct_narrative_citation_is_clean():
    assert run("Smith et al.~\\cite{smith2019} showed the effect persists.") == []


def test_naming_a_co_author_rather_than_the_first_is_clean():
    assert run("Roe et al.~\\cite{smith2019} showed the effect persists.") == []


def test_particled_surname_written_without_the_particle_is_clean():
    # BibTeX has "van Dijk"; prose conventionally shortens it to "Dijk".
    assert run("Dijk et al.~\\cite{vandijk2020} showed the effect.") == []


def test_accented_surname_matches_its_unaccented_spelling():
    assert run("Muller et al.~\\cite{muller2018} showed the effect.") == []


def test_capitalised_non_name_before_a_citation_is_clean():
    for phrase in (
        "Recent work",
        "Previous studies",
        "Section 3",
        "Table 2",
        "The model",
        "However, this",
        "Similarly, prior work",
    ):
        assert run(f"{phrase} et al.~\\cite{{jones2021}} is relevant.") == [], phrase


def test_bare_cite_without_et_al_or_year_is_clean():
    # No assertion in the prose means nothing for the entry to contradict.
    assert run("Smith \\cite{jones2021} showed the effect persists.") == []


def test_generative_commands_are_skipped():
    # \citet typesets the name from the entry, so it cannot disagree with it.
    for cmd in ("citet", "citep", "citeauthor", "citeyear"):
        assert run(f"Smith et al.~\\{cmd}{{jones2021}} showed the effect.") == [], cmd


def test_multi_key_citation_is_not_decidable():
    assert run("Smith et al.~\\cite{smith2019,jones2021} showed the effect.") == []


def test_undefined_key_is_left_to_the_undefined_citation_analyzer():
    assert run("Smith et al.~\\cite{nowhere2030} showed the effect.") == []


def test_entry_without_an_author_is_not_judged():
    assert run("Smith et al.~\\cite{noauthor2022} showed the effect.") == []


def test_two_named_authors_both_present_is_clean():
    assert run("Smith and Roe (2019) \\cite{smith2019} showed the effect.") == []


def test_citation_inside_a_listing_is_not_prose():
    tex = "\\begin{lstlisting}\nSmith et al.~\\cite{jones2021}\n\\end{lstlisting}"
    assert run(tex) == []


def test_no_suggestion_offered_when_nothing_matches():
    diags = run("Kowalski et al.~\\cite{jones2021} showed the effect.")
    assert len(diags) == 1
    assert diags[0].data["suggestion"] is None
    assert "Did you mean" not in diags[0].message


# -- surname extraction ------------------------------------------------------------------


def test_surnames_handles_both_bibtex_conventions():
    assert _surnames("Smith, Jane and Doe, John") == ["smith", "doe"]
    assert _surnames("Jane Smith and John Doe") == ["smith", "doe"]


def test_surnames_ignores_the_others_placeholder():
    assert _surnames("Smith, Jane and others") == ["smith"]


def test_surnames_strips_generational_suffixes():
    assert _surnames("John Smith Jr.") == ["smith"]


def test_surnames_of_empty_field_is_empty():
    assert _surnames("") == []
