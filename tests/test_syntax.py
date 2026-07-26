"""Unescaped-percent lint (AUR008).

The negative cases carry the weight here. A bare ``%`` is *usually* a deliberate comment,
so a check that fires on those is worse than no check at all — hence roughly three times
as many "must not flag" cases as "must flag" ones.
"""
from __future__ import annotations

from aurelius_ide.analyzers.syntax import UnescapedPercentAnalyzer
from aurelius_ide.diagnostics import Code, Severity

from .conftest import body, make_doc


def run(tex: str):
    return UnescapedPercentAnalyzer().run(make_doc(body(tex)))


# -- must flag ---------------------------------------------------------------------------


def test_flags_percent_after_integer():
    diags = run("We observed a 45% improvement in recall.")
    assert len(diags) == 1
    assert diags[0].code == Code.UNESCAPED_PERCENT
    assert diags[0].severity is Severity.WARNING


def test_flags_percent_after_decimal():
    assert len(run("Coverage rose to 99.9% of the corpus.")) == 1


def test_range_covers_exactly_the_percent_character():
    tex = body("We observed a 45% improvement.")
    doc = make_doc(tex)
    diag = UnescapedPercentAnalyzer().run(doc)[0]
    start = doc.text.index("45%") + 2
    assert doc.range_of(start, start + 1) == diag.range
    assert diag.range.end.character - diag.range.start.character == 1


def test_reports_the_text_that_would_be_dropped():
    diag = run("We observed a 45% improvement in recall.")[0]
    assert diag.data["dropped"] == "improvement in recall."
    assert diag.data["replacement"] == "\\%"


def test_flags_each_offending_line_independently():
    assert len(run("First 10% gain.\nSecond 20% gain.")) == 2


def test_percent_in_inline_math_is_still_a_comment():
    # Math mode does not turn off comments — $50%$ really does eat the closing delimiter.
    assert len(run("The value $50%$ is wrong.")) == 1


def test_only_the_first_percent_on_a_line_is_flagged():
    # Everything after the first one is inside the comment it opened.
    diags = run("Only 3% failed% and 9% more trailing text.")
    assert len(diags) == 1


# -- must not flag -----------------------------------------------------------------------


def test_escaped_percent_is_correct():
    assert run("We observed a 45\\% improvement in recall.") == []


def test_deliberate_comment_is_not_flagged():
    assert run("% TODO: revisit the 45% figure before submission") == []


def test_comment_after_a_number_with_a_space_is_not_flagged():
    # The adjacency requirement is what separates a comment from a literal percent.
    assert run("We set the threshold to 5 % explain this choice later") == []


def test_percent_encoded_url_is_not_flagged():
    assert run("See \\url{http://example.com/q?x=100%20y} for details.") == []


def test_percent_encoded_href_is_not_flagged():
    assert run("See \\href{http://example.com/?a=100%20b}{the data} for details.") == []


def test_verbatim_environment_is_not_flagged():
    assert run("\\begin{verbatim}\nprintf(\"50%d\", n);\n\\end{verbatim}") == []


def test_lstlisting_environment_is_not_flagged():
    assert run("\\begin{lstlisting}\nremainder = 7%2;\n\\end{lstlisting}") == []


def test_minted_environment_is_not_flagged():
    assert run("\\begin{minted}{c}\nint a = 7%2;\n\\end{minted}") == []


def test_percent_not_preceded_by_a_digit_is_not_flagged():
    assert run("The improvement was substantial % noted by reviewer 2") == []


def test_escaped_percent_followed_by_real_comment_is_clean():
    assert run("A 45\\% gain % and a genuine trailing comment") == []


def test_double_backslash_then_percent_is_a_real_comment():
    # \\ is a line break, so the % after it is not escaped — but nothing precedes it
    # that looks like a literal percent, so there is still nothing to report.
    assert run("End of row 3 \\\\% a comment after a line break") == []


def test_clean_document_produces_nothing():
    assert run("We report gains of 45\\% and 12\\% across both corpora.") == []
