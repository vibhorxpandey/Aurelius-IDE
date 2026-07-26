"""The verification boundary.

This is the only module that knows how a citation gets checked. Everything else depends
on the :class:`Verifier` protocol, which keeps three things true:

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
from typing import Any, Dict, Optional, Protocol, runtime_checkable


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

    def verify(self, citation: str) -> Dict[str, Any]:
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

    def verify(self, citation: str) -> Dict[str, Any]:
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
        self._offline: Optional[bool] = None

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

    def verify(self, citation: str) -> Dict[str, Any]:
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


_default: Optional[Verifier] = None


def get_default_verifier() -> Verifier:
    """Process-wide default: ``aurelius-mcp`` if importable, otherwise a null backend."""
    global _default
    if _default is None:
        candidate = AureliusVerifier()
        _default = candidate if candidate.available else NullVerifier()
    return _default


def set_default_verifier(verifier: Optional[Verifier]) -> None:
    """Override the default. Passing ``None`` restores lazy auto-detection."""
    global _default
    _default = verifier
