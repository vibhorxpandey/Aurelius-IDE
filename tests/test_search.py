"""Literature search and BibTeX generation.

No test here touches the network. :class:`OpenAlexSearcher` is exercised by replacing
``urlopen`` with a stub that replays a captured OpenAlex payload, which keeps the suite
hermetic while still testing the part with logic in it — flattening a work record and
rendering it as an entry someone can actually paste into a ``.bib``.
"""
from __future__ import annotations

import io
import json

import pytest

from aurelius_ide.verification import (
    NullSearcher,
    OpenAlexSearcher,
    _record_from_openalex,
    _suggest_key,
    get_default_searcher,
    set_default_searcher,
    to_bibtex,
)

# Trimmed from a real api.openalex.org/works response.
WORK = {
    "id": "https://openalex.org/W2963403868",
    "doi": "https://doi.org/10.48550/arxiv.1706.03762",
    "display_name": "Attention Is All You Need",
    "publication_year": 2017,
    "type": "proceedings-article",
    "cited_by_count": 103412,
    "is_retracted": False,
    "authorships": [
        {"author": {"display_name": "Ashish Vaswani"}},
        {"author": {"display_name": "Noam Shazeer"}},
    ],
    "primary_location": {"source": {"display_name": "Neural Information Processing Systems"}},
}

PAYLOAD = {"results": [WORK]}


class StubResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture(autouse=True)
def restore_default_searcher():
    yield
    set_default_searcher(None)


# -- record flattening -------------------------------------------------------------------


def test_record_carries_the_fields_the_editor_needs():
    r = _record_from_openalex(WORK)
    assert r["title"] == "Attention Is All You Need"
    assert r["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert r["year"] == "2017"
    assert r["venue"] == "Neural Information Processing Systems"
    assert r["cited_by"] == 103412


def test_doi_url_is_reduced_to_the_bare_identifier():
    # BibTeX wants 10.xxxx/yyyy, not the resolver URL OpenAlex returns.
    assert _record_from_openalex(WORK)["doi"] == "10.48550/arxiv.1706.03762"


def test_missing_fields_do_not_raise():
    r = _record_from_openalex({"display_name": "Bare"})
    assert r["authors"] == []
    assert r["year"] == ""
    assert r["venue"] == ""
    assert r["doi"] == ""


def test_null_primary_location_is_tolerated():
    # OpenAlex returns an explicit null here for unindexed works.
    r = _record_from_openalex({"display_name": "X", "primary_location": None})
    assert r["venue"] == ""


def test_retraction_flag_survives():
    assert _record_from_openalex({**WORK, "is_retracted": True})["is_retracted"] is True


# -- citation keys -----------------------------------------------------------------------


def test_key_is_first_author_surname_plus_year():
    assert _suggest_key(["Ashish Vaswani", "Noam Shazeer"], "2017", "T") == "vaswani2017"


def test_key_strips_accents_and_punctuation():
    assert _suggest_key(["Hans Müller"], "2018", "T") == "muller2018"


def test_key_falls_back_to_the_title_when_there_are_no_authors():
    assert _suggest_key([], "2020", "Anonymous Report") == "anonymous2020"


def test_key_without_a_year_is_just_the_surname():
    assert _suggest_key(["Jane Smith"], "", "T") == "smith"


# -- bibtex ------------------------------------------------------------------------------


def test_bibtex_uses_the_entry_type_matching_the_work():
    assert to_bibtex(_record_from_openalex(WORK)).startswith("@inproceedings{vaswani2017,")


def test_conference_papers_use_booktitle_not_journal():
    entry = to_bibtex(_record_from_openalex(WORK))
    assert "booktitle" in entry
    assert "journal" not in entry


def test_journal_articles_use_journal():
    work = {**WORK, "type": "article"}
    entry = to_bibtex(_record_from_openalex(work))
    assert "journal" in entry
    assert entry.startswith("@article{")


def test_title_is_brace_protected():
    # Without the extra braces, a BibTeX style lowercases the title and 'BERT' becomes
    # 'Bert' in the rendered bibliography.
    assert "title     = {{Attention Is All You Need}}" in to_bibtex(_record_from_openalex(WORK))


def test_authors_are_joined_with_and():
    assert "author    = {Ashish Vaswani and Noam Shazeer}" in to_bibtex(
        _record_from_openalex(WORK)
    )


def test_absent_fields_are_omitted_rather_than_left_empty():
    entry = to_bibtex(_record_from_openalex({"display_name": "Bare", "publication_year": 2001}))
    assert "doi" not in entry
    assert "author" not in entry
    assert "{Bare}" in entry


def test_generated_bibtex_round_trips_through_the_parser():
    """The whole point is that it can be pasted into a .bib and parsed back."""
    from aurelius_ide.document import parse_bibtex

    entries = parse_bibtex(to_bibtex(_record_from_openalex(WORK)))
    assert "vaswani2017" in entries
    parsed = entries["vaswani2017"]
    assert parsed.title == "Attention Is All You Need"
    assert parsed.year == "2017"
    assert parsed.entry_type == "inproceedings"


# -- the searcher ------------------------------------------------------------------------


def test_search_returns_flattened_records(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["agent"] = request.headers.get("User-agent", "")
        return StubResponse(json.dumps(PAYLOAD).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    results = OpenAlexSearcher().search("attention is all you need")

    assert len(results) == 1
    assert results[0]["key"] == "vaswani2017"
    assert "search=attention" in captured["url"]
    assert "aurelius-ide" in captured["agent"]


def test_mailto_is_sent_when_configured(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["agent"] = request.headers.get("User-agent", "")
        return StubResponse(json.dumps(PAYLOAD).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    OpenAlexSearcher(mailto="a@b.c").search("q")

    assert "mailto=a%40b.c" in captured["url"]
    assert "mailto:a@b.c" in captured["agent"]


def test_empty_query_does_not_hit_the_network(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("should not have made a request")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    assert OpenAlexSearcher().search("   ") == []


def test_limit_is_clamped_to_the_api_maximum(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return StubResponse(json.dumps({"results": []}).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    OpenAlexSearcher().search("q", limit=500)
    assert "per-page=25" in captured["url"]


def test_transport_failure_propagates_rather_than_reading_as_no_results(monkeypatch):
    """'The index is unreachable' must never be presentable as 'no such paper'."""

    def explode(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    with pytest.raises(OSError):
        OpenAlexSearcher().search("anything")


def test_null_searcher_raises_rather_than_returning_empty():
    with pytest.raises(RuntimeError):
        NullSearcher().search("q")


def test_default_searcher_is_openalex_and_overridable():
    assert isinstance(get_default_searcher(), OpenAlexSearcher)
    set_default_searcher(NullSearcher())
    assert get_default_searcher().name == "null"
