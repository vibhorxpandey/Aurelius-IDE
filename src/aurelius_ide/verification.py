"""The scholarly-index boundary.

This is the only module that reaches the network — both to *check* a citation the author
already wrote (:class:`Verifier`) and to *find* one they haven't (:class:`Searcher`). Both
live here rather than in a second module so that "what does this tool talk to?" has one
answer, auditable by reading one file.

Everything else depends on the :class:`Verifier` protocol, which keeps three things true:

* **The IDE has one soft dependency, isolated here.** ``aurelius-mcp`` supplies the
  scholarly lookup (OpenAlex → Crossref → arXiv → Semantic Scholar). If it isn't
  installed, the IDE still runs: structural analysis works and verification degrades to
  :class:`NullVerifier` rather than crashing on import.
* **Verification is swappable.** An institution with a licensed index, or a test suite
  that must not touch the network, provides its own object satisfying the protocol.
* **"I couldn't reach the index" is not "the index says no."**

That last point is a correctness fix, not a nicety. The naive implementation reports a
network failure as ``not_found``, which renders in the editor as *every reference in your
bibliography is fabricated*. That is the single worst possible false positive for a tool
whose entire pitch is research integrity: it is alarming, it is wrong, and it appears
precisely when the user is on a plane and least able to check. :class:`VerdictKind.ERROR`
exists so transport failure stays silent.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable


class VerdictKind(str, Enum):
    """Outcome of a verification attempt.

    ``ERROR`` is deliberately distinct from ``NOT_FOUND``. The first means we do not know;
    the second means we asked and the answer was no. Only the second is a finding.
    """

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_FOUND = "not_found"
    RETRACTED = "retracted"
    ERROR = "error"


#: Verdicts that indicate we failed to obtain an answer and must not report a diagnostic.
INCONCLUSIVE = frozenset({VerdictKind.ERROR})


@runtime_checkable
class Verifier(Protocol):
    """Checks whether a citation refers to a real, correctly-attributed work."""

    name: str

    def verify(self, citation: str) -> dict[str, Any]:
        """Return a verdict dict.

        Required keys: ``ok`` (bool), ``verdict`` (:class:`VerdictKind` value).
        Optional: ``confidence``, ``notes``, ``matched_work``, ``author_match``,
        ``corrected_citation``, ``bibtex``.
        """
        ...


class NullVerifier:
    """Fallback when no verification backend is available.

    Reports ``ERROR`` for everything, which the analyzer treats as inconclusive and
    silent. An IDE with no verifier is a structural linter — still useful, and honest
    about what it does not know.
    """

    name = "null"

    def verify(self, citation: str) -> dict[str, Any]:
        return {
            "ok": False,
            "verdict": VerdictKind.ERROR.value,
            "notes": "No verification backend installed (pip install aurelius-mcp).",
        }


# Exception types that mean "the network failed", not "the work does not exist".
_TRANSPORT_ERROR_NAMES = frozenset(
    {
        "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout",
        "TimeoutException", "NetworkError", "ProxyError", "RemoteProtocolError",
        "TransportError", "OSError", "SSLError", "ReadError", "socket.gaierror",
    }
)


def _is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError | TimeoutError):
        return True
    return type(exc).__name__ in _TRANSPORT_ERROR_NAMES


class AureliusVerifier:
    """Scholarly verification backed by ``aurelius-mcp``.

    Wraps :func:`aurelius.tools.scholarly.verify_citation` and adds the distinction the
    underlying function cannot make on its own: it returns ``not_found`` both when every
    index genuinely lacks the work and when every index was unreachable. We probe
    connectivity once, lazily, and downgrade a suspicious ``not_found`` to ``ERROR`` when
    the network is down.
    """

    name = "aurelius"

    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results
        self._verify_citation = None
        self._offline: bool | None = None

    @property
    def available(self) -> bool:
        return self._load() is not None

    def _load(self):
        if self._verify_citation is None:
            try:
                from aurelius.tools.scholarly import verify_citation
            except ImportError:
                return None
            self._verify_citation = verify_citation
        return self._verify_citation

    def _probe_network(self) -> bool:
        """One cheap reachability check against a scholarly index.

        Cached for the process lifetime: a per-citation probe would double request volume,
        and a session that starts offline and comes back online is rare enough that a
        restart is an acceptable remedy.
        """
        if self._offline is not None:
            return not self._offline
        try:
            import httpx

            with httpx.Client(timeout=4.0) as client:
                client.head("https://api.openalex.org/works")
            self._offline = False
        except Exception:
            self._offline = True
        return not self._offline

    def verify(self, citation: str) -> dict[str, Any]:
        fn = self._load()
        if fn is None:
            return NullVerifier().verify(citation)

        try:
            result = fn(citation, max_results=self.max_results)
        except Exception as exc:
            # Every exception is ERROR, transport or not: a backend that raised did not
            # tell us the work is missing, so per invariant 4 we stay silent either way.
            # The distinction survives only in the note, because "you are offline" and
            # "the verifier is broken" call for different actions from the user.
            note = (
                "Offline — citation could not be checked against any index."
                if _is_transport_error(exc)
                else f"Verification backend failed: {type(exc).__name__}."
            )
            return {"ok": False, "verdict": VerdictKind.ERROR.value, "notes": note}

        # A 'not_found' from an unreachable network is an artefact, not a finding.
        if result.get("verdict") == VerdictKind.NOT_FOUND.value and not self._probe_network():
            return {
                "ok": False,
                "verdict": VerdictKind.ERROR.value,
                "notes": "Offline — citation could not be checked against any index.",
            }
        return result


# --------------------------------------------------------------------------------------
# Literature search — the other direction across the same boundary
# --------------------------------------------------------------------------------------


@runtime_checkable
class Searcher(Protocol):
    """Finds candidate works for a free-text query."""

    name: str

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return candidate records, best match first.

        Each record carries ``key``, ``title``, ``authors`` (list), ``year``, ``doi``,
        ``venue``, ``cited_by`` and ``bibtex``. An empty list means "nothing found"; a
        failure to reach the index raises, so the caller can tell the two apart.
        """
        ...


class NullSearcher:
    """Fallback when no search backend is configured. Finds nothing, fails loudly."""

    name = "null"

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        raise RuntimeError("No literature-search backend is configured.")


class OpenAlexSearcher:
    """Keyless literature search against OpenAlex, using only the standard library.

    Deliberately *not* routed through ``aurelius-mcp``. Search is the feature that gets a
    new user to their first verified citation, so it must work on a bare
    ``pip install aurelius-ide`` with no extras and no API key. OpenAlex is free, keyless,
    and asks only that you identify yourself — hence the mailto in the User-Agent, which
    is their documented way into the faster rate-limit pool.
    """

    name = "openalex"
    endpoint = "https://api.openalex.org/works"

    def __init__(self, mailto: str = "", timeout: float = 8.0) -> None:
        self.mailto = mailto
        self.timeout = timeout

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        import json
        import urllib.parse
        import urllib.request

        query = query.strip()
        if not query:
            return []

        params = {"search": query, "per-page": str(max(1, min(limit, 25)))}
        if self.mailto:
            params["mailto"] = self.mailto
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"

        agent = "aurelius-ide"
        if self.mailto:
            agent += f" (mailto:{self.mailto})"
        request = urllib.request.Request(url, headers={"User-Agent": agent})

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return [_record_from_openalex(w) for w in payload.get("results", [])]


def _record_from_openalex(work: dict[str, Any]) -> dict[str, Any]:
    """Flatten one OpenAlex work into the shape the editor consumes."""
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    location = work.get("primary_location") or {}
    source = location.get("source") or {}

    # OpenAlex returns the DOI as a full URL; BibTeX wants the bare identifier.
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    year = str(work.get("publication_year") or "")
    title = work.get("display_name") or work.get("title") or ""

    record = {
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        "venue": source.get("display_name") or "",
        "cited_by": work.get("cited_by_count") or 0,
        "type": work.get("type") or "article",
        "is_retracted": bool(work.get("is_retracted")),
        "openalex": work.get("id") or "",
    }
    record["key"] = _suggest_key(authors, year, title)
    record["bibtex"] = to_bibtex(record)
    return record


def _suggest_key(authors: list[str], year: str, title: str) -> str:
    """Build a conventional ``surnameYEAR`` citation key."""
    import re
    import unicodedata

    surname = ""
    if authors:
        parts = authors[0].split()
        surname = parts[-1] if parts else ""
    if not surname:
        surname = (title.split() or ["work"])[0]

    folded = unicodedata.normalize("NFKD", surname)
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c))
    stem = re.sub(r"[^a-z]", "", ascii_only.lower()) or "work"
    return f"{stem}{year}" if year else stem


#: OpenAlex work types that map onto a BibTeX entry type other than @article.
_BIBTEX_TYPE = {
    "book": "book",
    "book-chapter": "incollection",
    "dissertation": "phdthesis",
    "proceedings-article": "inproceedings",
    "report": "techreport",
}


def to_bibtex(record: dict[str, Any]) -> str:
    """Render a search record as a BibTeX entry.

    Titles are wrapped in an extra brace group because BibTeX styles lowercase titles by
    default, and a paper about ``BERT`` must not be typeset as ``Bert``.
    """
    entry_type = _BIBTEX_TYPE.get(record.get("type", ""), "article")
    fields: list[tuple[str, str]] = []

    authors = record.get("authors") or []
    if authors:
        fields.append(("author", " and ".join(authors)))
    if record.get("title"):
        fields.append(("title", "{" + record["title"] + "}"))
    if record.get("venue"):
        key = "booktitle" if entry_type == "inproceedings" else "journal"
        fields.append((key, record["venue"]))
    if record.get("year"):
        fields.append(("year", record["year"]))
    if record.get("doi"):
        fields.append(("doi", record["doi"]))

    width = max((len(name) for name, _ in fields), default=0)
    body = ",\n".join(f"  {name.ljust(width)} = {{{value}}}" for name, value in fields)
    return f"@{entry_type}{{{record.get('key', 'work')},\n{body}\n}}"


_default: Verifier | None = None
_default_searcher: Searcher | None = None


def get_default_searcher() -> Searcher:
    """Process-wide default search backend."""
    global _default_searcher
    if _default_searcher is None:
        _default_searcher = OpenAlexSearcher()
    return _default_searcher


def set_default_searcher(searcher: Searcher | None) -> None:
    """Override the default. Passing ``None`` restores the OpenAlex backend."""
    global _default_searcher
    _default_searcher = searcher


def get_default_verifier() -> Verifier:
    """Process-wide default: ``aurelius-mcp`` if importable, otherwise a null backend."""
    global _default
    if _default is None:
        candidate = AureliusVerifier()
        _default = candidate if candidate.available else NullVerifier()
    return _default


def set_default_verifier(verifier: Verifier | None) -> None:
    """Override the default. Passing ``None`` restores lazy auto-detection."""
    global _default
    _default = verifier
