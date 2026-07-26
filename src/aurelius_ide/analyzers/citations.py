"""Citation analyzers — the core of the linter.

Four checks, split by cost:

* :class:`UndefinedCitationAnalyzer` — a ``\\cite{}`` key with no BibTeX entry. This is the
  research equivalent of an unresolved symbol, and it is the single most common cause of
  ``[?]`` marks in a compiled paper. Instant.
* :class:`UnusedBibEntryAnalyzer` — an entry nothing cites. Harmless to a build but a
  reliable signal of a bibliography drifting out of sync with the text. Instant.
* :class:`IncompleteBibEntryAnalyzer` — entries missing the fields their type requires.
  Instant, and it catches the entries that would silently render as garbage.
* :class:`ScholarlyVerificationAnalyzer` — does the cited work actually *exist*, is it by
  the claimed authors, and has it been retracted? Network-bound, cached per entry.

Only the last one needs the internet, and it is the only one that can catch a
hallucinated reference — which is why it is the reason this project exists.
"""
from __future__ import annotations

from typing import Any

from ..cache import ResultCache
from ..diagnostics import Code, Diagnostic, Severity
from ..document import BibEntry, ResearchDocument
from ..verification import INCONCLUSIVE, VerdictKind, Verifier, get_default_verifier
from .base import BaseAnalyzer

# Fields BibTeX itself will complain about, by entry type.
_REQUIRED_FIELDS: dict[str, tuple] = {
    "article": ("author", "title", "journal", "year"),
    "inproceedings": ("author", "title", "booktitle", "year"),
    "book": ("author", "title", "publisher", "year"),
    "techreport": ("author", "title", "institution", "year"),
    "phdthesis": ("author", "title", "school", "year"),
    "mastersthesis": ("author", "title", "school", "year"),
    "misc": ("title",),
}


class UndefinedCitationAnalyzer(BaseAnalyzer):
    """``\\cite{key}`` where ``key`` is not in the bibliography."""

    name = "undefined_citation"
    is_network = False

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        known = set(doc.bib_entries)
        for ref in doc.undefined_keys():
            suggestion = _closest_key(ref.key, known)
            message = f"Undefined citation key '{ref.key}' — no entry in the bibliography."
            if suggestion:
                message += f" Did you mean '{suggestion}'?"
            out.append(
                Diagnostic(
                    range=doc.range_of(ref.start, ref.end),
                    message=message,
                    severity=Severity.ERROR,
                    code=Code.UNDEFINED_CITATION,
                    data={"key": ref.key, "suggestion": suggestion},
                )
            )
        return out


class UnusedBibEntryAnalyzer(BaseAnalyzer):
    """A bibliography entry that nothing in the document cites."""

    name = "unused_bib_entry"
    is_network = False

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:
        # Ranges point into the .bib file, so they are only meaningful when the client
        # knows that URI. The engine routes these separately.
        return [
            Diagnostic(
                range=doc.bib_range_of(e.start, e.end),
                message=f"'{e.key}' is never cited in the document.",
                severity=Severity.HINT,
                code=Code.UNUSED_BIB_ENTRY,
                data={"key": e.key, "uri": doc.bib_uri},
            )
            for e in doc.unused_entries()
        ]


class IncompleteBibEntryAnalyzer(BaseAnalyzer):
    """Entries missing fields that their type requires."""

    name = "incomplete_bib_entry"
    is_network = False

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        for entry in doc.bib_entries.values():
            required = _REQUIRED_FIELDS.get(entry.entry_type)
            if not required:
                continue
            missing = [f for f in required if not entry.fields.get(f)]
            if missing:
                out.append(
                    Diagnostic(
                        range=doc.bib_range_of(entry.start, entry.end),
                        message=(
                            f"@{entry.entry_type} '{entry.key}' is missing required "
                            f"field(s): {', '.join(missing)}."
                        ),
                        severity=Severity.WARNING,
                        code=Code.INCOMPLETE_BIB_ENTRY,
                        data={"key": entry.key, "missing": missing, "uri": doc.bib_uri},
                    )
                )
        return out


class ScholarlyVerificationAnalyzer(BaseAnalyzer):
    """Verify each cited entry against OpenAlex / Crossref / arXiv / Semantic Scholar.

    Diagnostics land on the *citation sites* in the ``.tex``, not on the bibliography,
    because that is where the author is looking when they make the claim. One bad entry
    cited five times produces five squiggles, which is the correct behaviour: every one
    of those five sentences is unsupported.

    Only entries that are actually cited get verified — an unused entry costs nothing to
    leave unchecked, and skipping them keeps a bloated ``.bib`` from burning the network
    budget.
    """

    name = "scholarly_verification"
    is_network = True

    def __init__(
        self,
        cache: ResultCache | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self.cache = cache or ResultCache()
        self.verifier = verifier or get_default_verifier()

    def _fetch(self, citation: str) -> dict[str, Any]:
        """The single network call. Overridden in tests to keep them hermetic.

        Kept separate from :meth:`verify_entry` so that cache policy and transport can be
        tested independently — a stub that replaced the cached method would silently make
        the cache untested.
        """
        return self.verifier.verify(citation)

    def verify_entry(self, entry: BibEntry) -> dict[str, Any]:
        """Cached single-entry verification. Public so the engine can warm entries."""
        h = entry.content_hash()
        hit = self.cache.get(self.name, h)
        if hit is not None:
            return hit
        try:
            result = self._fetch(entry.as_citation_string())
        except Exception as exc:  # network/parse failures must never kill the analyzer
            return {"ok": False, "verdict": "error", "notes": str(exc)[:200]}
        self.cache.set(self.name, h, result)
        return result

    def run(self, doc: ResearchDocument) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        cited = {r.key for r in doc.cite_refs}
        verdicts: dict[str, dict[str, Any]] = {}

        for key in cited:
            entry = doc.bib_entries.get(key)
            if entry is None:
                continue  # UndefinedCitationAnalyzer already reported this
            verdicts[key] = self.verify_entry(entry)

        for ref in doc.cite_refs:
            result = verdicts.get(ref.key)
            if not result or not result.get("ok"):
                continue
            diag = _diagnostic_for(result, ref.key)
            if diag is None:
                continue
            severity, message, code = diag
            out.append(
                Diagnostic(
                    range=doc.range_of(ref.start, ref.end),
                    message=message,
                    severity=severity,
                    code=code,
                    data={
                        "key": ref.key,
                        "verdict": result.get("verdict"),
                        "matched_work": result.get("matched_work"),
                        "corrected_citation": result.get("corrected_citation"),
                        "bibtex": result.get("bibtex"),
                        "notes": result.get("notes"),
                    },
                )
            )
        return out


def _diagnostic_for(result: dict[str, Any], key: str):
    """Map a verification verdict to (severity, message, code), or None if clean.

    An inconclusive verdict produces nothing. Reporting "could not be verified" when the
    cause was a dropped connection teaches users to ignore the linter, which is worse
    than saying nothing at all.
    """
    verdict = result.get("verdict")
    if verdict in {v.value for v in INCONCLUSIVE}:
        return None
    notes = result.get("notes") or ""

    if verdict == VerdictKind.RETRACTED.value:
        return (
            Severity.ERROR,
            f"'{key}' cites a RETRACTED work. {notes}",
            Code.RETRACTED_CITATION,
        )
    if verdict == VerdictKind.NOT_FOUND.value:
        return (
            Severity.ERROR,
            f"'{key}' could not be found in any scholarly index. {notes}",
            Code.UNVERIFIED_CITATION,
        )
    if verdict == VerdictKind.UNVERIFIED.value:
        # The author-mismatch case is materially different from "no record at all": the
        # paper exists but is probably not the one being cited.
        if result.get("author_match") is False and result.get("matched_work"):
            return (
                Severity.WARNING,
                f"'{key}' — title matched but authors differ. {notes}",
                Code.AUTHOR_MISMATCH,
            )
        return (
            Severity.WARNING,
            f"'{key}' could not be verified. {notes}",
            Code.UNVERIFIED_CITATION,
        )
    if verdict == VerdictKind.VERIFIED.value and result.get("confidence") == "medium":
        return (
            Severity.INFORMATION,
            f"'{key}' verified with medium confidence. {notes}",
            Code.UNVERIFIED_CITATION,
        )
    return None


def _closest_key(target: str, candidates) -> str | None:
    """Cheap edit-distance suggestion for a mistyped key."""
    import difflib

    matches = difflib.get_close_matches(target, list(candidates), n=1, cutoff=0.75)
    return matches[0] if matches else None
