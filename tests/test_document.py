"""Document model: LaTeX lexing, masking, sentence segmentation, BibTeX parsing."""
from __future__ import annotations

from aurelius_ide.document import PositionIndex, ResearchDocument, parse_bibtex

from .conftest import BIB, make_doc

# -- position index ---------------------------------------------------------------------


def test_position_index_maps_offsets_to_line_and_character():
    idx = PositionIndex("abc\ndefg\n\nhi")
    assert (idx.position(0).line, idx.position(0).character) == (0, 0)
    assert (idx.position(4).line, idx.position(4).character) == (1, 0)
    assert (idx.position(6).line, idx.position(6).character) == (1, 2)
    assert idx.position(9).line == 2
    assert idx.position(10).line == 3


def test_position_index_clamps_out_of_range_offsets():
    idx = PositionIndex("ab")
    assert idx.position(-5).character == 0
    assert idx.position(999).line == 0


# -- citation extraction ------------------------------------------------------------------


def test_parses_cite_family_and_splits_multiple_keys():
    doc = make_doc(r"\begin{document}Text \citep{smith2020, jones2021} more.\end{document}")
    assert [r.key for r in doc.cite_refs] == ["smith2020", "jones2021"]
    assert all(r.command == "citep" for r in doc.cite_refs)


def test_each_key_span_covers_only_that_key():
    tex = r"\begin{document}\citep{smith2020, jones2021}\end{document}"
    doc = make_doc(tex)
    for ref in doc.cite_refs:
        assert tex[ref.start : ref.end] == ref.key


def test_optional_arguments_do_not_break_key_extraction():
    doc = make_doc(r"\begin{document}\citep[see][p.~4]{smith2020}\end{document}")
    assert [r.key for r in doc.cite_refs] == ["smith2020"]


def test_all_cite_command_variants_are_recognised():
    tex = (
        r"\begin{document}\cite{smith2020}\citet{jones2021}"
        r"\citeauthor{smith2020}\nocite{never_cited}\end{document}"
    )
    commands = {r.command for r in make_doc(tex).cite_refs}
    assert commands == {"cite", "citet", "citeauthor", "nocite"}


def test_cite_ref_at_offset_locates_the_key_under_the_cursor():
    tex = r"\begin{document}\citep{smith2020}\end{document}"
    doc = make_doc(tex)
    assert doc.cite_ref_at(tex.index("smith2020") + 2).key == "smith2020"
    assert doc.cite_ref_at(0) is None


# -- masking --------------------------------------------------------------------------------


def test_citations_inside_comments_are_ignored():
    doc = make_doc("\\begin{document}\n% \\citep{smith2020}\nreal text\n\\end{document}")
    assert doc.cite_refs == []


def test_escaped_percent_does_not_start_a_comment():
    doc = make_doc(r"\begin{document}Growth was 12\% \citep{smith2020}.\end{document}")
    assert [r.key for r in doc.cite_refs] == ["smith2020"]


def test_inline_math_is_masked_from_prose():
    doc = make_doc(r"\begin{document}Let $x = 45\%$ hold.\end{document}")
    assert "45" not in " ".join(s.text for s in doc.sentences)


def test_display_math_environments_are_masked():
    tex = (
        "\\begin{document}\n\\begin{equation}\nE = 99\\% mc^2\n\\end{equation}\n"
        "Real prose here.\n\\end{document}"
    )
    assert "99" not in " ".join(s.text for s in make_doc(tex).sentences)


def test_verbatim_blocks_are_masked():
    tex = (
        "\\begin{document}\n\\begin{lstlisting}\naccuracy = 0.95\n\\end{lstlisting}\n"
        "Prose follows.\n\\end{document}"
    )
    assert "0.95" not in " ".join(s.text for s in make_doc(tex).sentences)


def test_masking_preserves_offsets_so_ranges_stay_valid():
    """Masking blanks characters rather than deleting them, so every offset computed
    against the masked text still indexes the original document."""
    tex = "\\begin{document}\n% a comment\nThe claim is here \\citep{smith2020}.\n\\end{document}"
    doc = make_doc(tex)
    ref = doc.cite_refs[0]
    assert tex[ref.start : ref.end] == "smith2020"


# -- sentences -------------------------------------------------------------------------------


def test_sections_are_tracked_and_attached_to_sentences():
    tex = (
        "\\begin{document}\n\\section{Introduction}\nFirst claim here.\n"
        "\\section{Results}\nSecond claim here.\n\\end{document}"
    )
    doc = make_doc(tex)
    assert [s.title for s in doc.sections] == ["Introduction", "Results"]
    sections = {s.section for s in doc.sentences if s.text}
    assert "Introduction" in sections and "Results" in sections


def test_sentence_spans_exclude_surrounding_whitespace():
    doc = make_doc("\\begin{document}\n  One sentence here.  \n\\end{document}")
    target = [s for s in doc.sentences if "One sentence" in s.text][0]
    assert not doc.text[target.start].isspace()
    assert not doc.text[target.end - 1].isspace()


def test_abbreviations_do_not_terminate_sentences():
    doc = make_doc(r"\begin{document}We follow Smith et al. in this respect here.\end{document}")
    assert len([s for s in doc.sentences if "Smith" in s.text]) == 1


def test_initials_do_not_terminate_sentences():
    doc = make_doc(
        r"\begin{document}The method of R. A. Fisher applies directly here.\end{document}"
    )
    assert len([s for s in doc.sentences if "Fisher" in s.text]) == 1


def test_section_titles_do_not_become_sentences():
    tex = (
        "\\begin{document}\n\\section{A Very Long Section Title Indeed}\n"
        "Body text.\n\\end{document}"
    )
    assert not any("Very Long Section" in s.text for s in make_doc(tex).sentences)


# -- bibtex ------------------------------------------------------------------------------------


def test_parse_bibtex_extracts_keys_and_fields():
    entries = parse_bibtex(BIB)
    assert set(entries) == {"smith2020", "jones2021", "never_cited"}
    assert entries["smith2020"].year == "2020"
    assert entries["smith2020"].doi == "10.1234/things"


def test_parse_bibtex_strips_protective_braces_from_values():
    """``{BERT}`` protects capitalisation in BibTeX but would never match an index title."""
    assert parse_bibtex(BIB)["jones2021"].title == "Nested BRACES in a Title"


def test_parse_bibtex_ignores_comment_and_string_directives():
    text = '@string{acm = "ACM"}\n@comment{ignored}\n@article{real, title={T}, year={2020}}'
    assert set(parse_bibtex(text)) == {"real"}


def test_parse_bibtex_accepts_quoted_values():
    entries = parse_bibtex('@article{k, title = "Quoted Title", year = 2020}')
    assert entries["k"].title == "Quoted Title"
    assert entries["k"].year == "2020"


def test_citation_string_round_trip_includes_identifying_fields():
    s = parse_bibtex(BIB)["smith2020"].as_citation_string()
    assert "Smith" in s and "2020" in s and "A Study of Things" in s


def test_content_hash_ignores_formatting_but_tracks_meaning():
    a = parse_bibtex("@article{k, title={T}, year={2020}}")["k"]
    b = parse_bibtex("@article{k,\n  year = {2020},\n  title = {T}\n}")["k"]
    c = parse_bibtex("@article{k, title={T}, year={2021}}")["k"]
    assert a.content_hash() == b.content_hash()
    assert a.content_hash() != c.content_hash()


def test_bibliography_has_its_own_position_index():
    doc = ResearchDocument.parse("file:///p.tex", r"\begin{document}\end{document}", 1, BIB)
    entry = doc.bib_entries["never_cited"]
    rng = doc.bib_range_of(entry.start, entry.end)
    assert "never_cited" in BIB.splitlines()[rng.start.line]
