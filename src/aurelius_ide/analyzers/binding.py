"""Claim-to-source binding — does the sentence cite the paper it says it cites?

Every other check in this project asks whether a reference is *real*. This one asks
whether it is the *right* one, which is a different failure and a more embarrassing one:

    Smith et al. (2019) showed that the effect persists \\cite{jones2021}.

Both keys resolve. Both works exist. Neither is retracted. The bibliography is immaculate.
The sentence still attributes a finding to the wrong paper, and no existing check has any
opinion about it. It survives peer review routinely, because a reader has to open the
bibliography and cross-check by hand to catch it.

Full claim-to-source binding — does this paper actually *support* this assertion — needs
semantics we do not have and cannot get from a stdlib parser. What we can do soundly is
check the part the author already wrote down twice. A *narrative* citation states the
author and year in prose; the ``\\cite`` key states them again via the bibliography. When
those two disagree, one of them is wrong, and that is decidable with string comparison.

The check therefore fires only on citations that name a source in prose:

* ``Smith et al.~\\cite{k}`` — ``et al.`` guarantees the preceding word is a surname.
* ``Smith (2019) \\cite{k}`` — a parenthetical year does the same job.

A bare ``\\cite{k}`` after an ordinary capitalised word claims nothing and is ignored;
without one of those two markers there is no second assertion to contradict, and guessing
which capitalised words are names is how this check would start crying wolf. ``\\citet``
and ``\\citep`` generate the name and year from the entry itself, so they cannot
disagree with it and are skipped.

Being wrong in prose and being wrong in the key are the same diagnostic, because the tool
cannot tell which side the author meant. When some *other* entry in the bibliography does
match the prose, that entry is offered as the fix — usually it is the one intended, and
the mistake was a stale key left behind by an edit.
"""
from __future__ import annotations

import re
import unicodedata

from ..diagnostics import Code, Diagnostic, Severity
from ..document import BibEntry, ResearchDocument
from .base import BaseAnalyzer

#: A narrative citation: a surname, optionally "and Other" or "et al.", optionally a
#: parenthetical year, then a \cite command. ``et al.`` or the year must be present —
#: that requirement is the entire false-positive defence, so do not relax it.
_NARRATIVE_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z'’\-]+)"
    r"(?:\s*(?:,|\s)\s*(?:and|&)\s*(?P<name2>[A-Z][A-Za-z'’\-]+))?"
    r"(?P<etal>\s*et\s+al\.?)?"
    r"(?:\s*[\(\[](?P<year>1[6-9]\d{2}|20\d{2})[\)\]])?"
    r"[\s~]*"
    r"\\(?P<cmd>cite[a-zA-Z]*|nocite)"
    r"(?:\s*\[[^\]]*\])*"
    r"\s*\{(?P<keys>[^}]*)\}"
)

#: ``\citet``/``\citep``/``\citeauthor`` and friends typeset the author and year from the
#: entry, so a name in front of them is the *previous* sentence's word, not a claim about
#: this key. Only the plain forms assert anything the entry could contradict.
_GENERATIVE_COMMANDS = frozenset({"citet", "citep", "citealt", "citealp", "citeauthor", "citeyear"})

#: Capitalised words that precede a citation without naming anybody. "Recent work
#: \cite{k}" must never be read as a surname of "Recent".
_NOT_A_SURNAME = frozenset(
    {
        "the", "this", "that", "these", "those", "we", "our", "us", "it", "its",
        "in", "on", "at", "by", "for", "from", "with", "and", "but", "or", "as",
        "section", "table", "figure", "fig", "equation", "eq", "appendix", "chapter",
        "algorithm", "listing", "theorem", "lemma", "corollary", "definition", "step",
        "recent", "previous", "prior", "earlier", "later", "related", "other", "others",
        "however", "moreover", "furthermore", "additionally", "also", "similarly",
        "therefore", "thus", "hence", "consequently", "finally", "first", "second",
        "third", "notably", "interestingly", "specifically", "importantly", "here",
        "both", "all", "many", "several", "some", "most", "such", "work", "works",
        "study", "studies", "research", "results", "method", "methods", "approach",
        "model", "models", "dataset", "datasets", "data", "see", "cf", "e.g", "i.e",
        "using", "based", "following", "unlike", "although", "while", "when", "since",
    }
)


class CitationBindingAnalyzer(BaseAnalyzer):
    """Flag a narrative citation whose prose disagrees with the entry it cites."""

    name = "citation_binding"
    is_network = False

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        masked = _masked_view(doc)

        for m in _NARRATIVE_RE.finditer(masked):
            if m.group("cmd") in _GENERATIVE_COMMANDS:
                continue
            # Without "et al." or a year there is no assertion to contradict.
            if not m.group("etal") and not m.group("year"):
                continue

            name = m.group("name")
            if name.lower() in _NOT_A_SURNAME:
                continue

            keys = [k.strip() for k in m.group("keys").split(",") if k.strip()]
            if len(keys) != 1:
                # "Smith et al. \cite{a,b}" attributes to a group; the prose names only
                # the lead work and disagreement is not decidable.
                continue
            key = keys[0]

            entry = doc.bib_entries.get(key)
            if entry is None:
                continue  # UndefinedCitationAnalyzer owns this one.

            prose_names = [n for n in (name, m.group("name2")) if n]
            year = m.group("year")
            problem = _mismatch(entry, prose_names, year)
            if problem is None:
                continue

            suggestion = _better_key(doc.bib_entries, prose_names, year, exclude=key)
            message = (
                f"Narrative citation says {_render(prose_names, bool(m.group('etal')), year)} "
                f"but '{key}' is {_describe(entry)} — {problem}."
            )
            if suggestion:
                message += f" Did you mean '{suggestion}'?"

            start, end = m.start("name"), m.end("keys") + 1
            out.append(
                Diagnostic(
                    range=doc.range_of(start, end),
                    message=message,
                    severity=Severity.WARNING,
                    code=Code.CITATION_BINDING,
                    data={
                        "key": key,
                        "prose_names": prose_names,
                        "prose_year": year,
                        "entry_author": entry.author,
                        "entry_year": entry.year,
                        "suggestion": suggestion,
                        "mismatch": problem,
                    },
                )
            )
        return out


# --------------------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------------------


def _masked_view(doc: ResearchDocument) -> str:
    """Text with literal regions blanked, at unchanged offsets.

    A ``\\cite`` inside ``lstlisting`` is example code in a methods section, not a claim.
    Blanking rather than removing keeps every offset usable against ``doc.text``.
    """
    if not doc.literal_spans:
        return doc.text
    chars = list(doc.text)
    for start, end in doc.literal_spans:
        for i in range(max(0, start), min(len(chars), end)):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _mismatch(entry: BibEntry, prose_names: list[str], year: str | None) -> str | None:
    """Describe how the entry contradicts the prose, or ``None`` if it is consistent."""
    surnames = _surnames(entry.author)
    if surnames and prose_names:
        if not any(_name_matches(n, surnames) for n in prose_names):
            shown = " and ".join(prose_names)
            return f"no author named {shown}"

    if year and entry.year and year != entry.year:
        return f"the year is {entry.year}, not {year}"
    return None


def _name_matches(prose_name: str, surnames: list[str]) -> bool:
    """Match a prose surname against an entry's authors, tolerantly.

    Compound and particled surnames are written inconsistently between prose and BibTeX
    — "van Dijk" cited as "Dijk", "Garcia-Lopez" as "Garcia" — so a component match
    counts. Being generous here costs recall, which is the direction this check should
    err in.
    """
    target = _fold(prose_name)
    if len(target) < 3:
        return True  # too short to judge; stay quiet
    for surname in surnames:
        if target == surname:
            return True
        parts = re.split(r"[\s\-]+", surname)
        if target in parts:
            return True
        if len(target) >= 5 and (target in surname or surname in target):
            return True
    return False


_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})


def _surnames(author_field: str) -> list[str]:
    """Extract folded surnames from a BibTeX ``author`` field.

    Handles both conventions — ``Smith, Jane and Doe, John`` and ``Jane Smith and John
    Doe`` — because ``.bib`` files in the wild mix them freely, sometimes within one file.
    """
    out: list[str] = []
    for part in re.split(r"\s+and\s+", author_field):
        part = part.strip().rstrip(".,")
        if not part or part.lower() == "others":
            continue
        if "," in part:
            surname = part.split(",")[0]
        else:
            tokens = part.split()
            if not tokens:
                continue
            # Trailing suffixes are not the surname: "John Smith Jr" is Smith.
            while len(tokens) > 1 and tokens[-1].lower().rstrip(".") in _SUFFIXES:
                tokens.pop()
            surname = tokens[-1]
        folded = _fold(surname)
        if folded:
            out.append(folded)
    return out


def _fold(name: str) -> str:
    """Lowercase and strip accents/punctuation so 'Müller' matches 'Muller'."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z\s\-]", "", ascii_only.lower()).strip()


def _better_key(
    entries: dict[str, BibEntry],
    prose_names: list[str],
    year: str | None,
    exclude: str,
) -> str | None:
    """Find an entry that *does* match the prose — usually the key the author meant.

    Only returned when exactly one entry matches. Two candidates means we would be
    guessing, and a quick fix that picks the wrong paper is worse than no quick fix.
    """
    matches = []
    for key, entry in entries.items():
        if key == exclude:
            continue
        surnames = _surnames(entry.author)
        if not surnames:
            continue
        if not any(_name_matches(n, surnames) for n in prose_names):
            continue
        if year and entry.year and entry.year != year:
            continue
        matches.append(key)
    return matches[0] if len(matches) == 1 else None


def _render(names: list[str], et_al: bool, year: str | None) -> str:
    text = " and ".join(names)
    if et_al:
        text += " et al."
    if year:
        text += f" ({year})"
    return text


def _describe(entry: BibEntry) -> str:
    surnames = _surnames(entry.author)
    who = surnames[0].title() if surnames else "an entry with no author"
    if len(surnames) > 1:
        who += " et al."
    return f"{who} ({entry.year})" if entry.year else who
