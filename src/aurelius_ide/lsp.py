"""Language Server Protocol front end.

This is the only module that depends on ``pygls``; everything it does is transport. The
analysis lives in :mod:`aurelius.ide.engine` and is equally usable from a CLI, a CI gate,
or a web backend.

Wiring notes worth knowing:

* **Bibliography discovery.** A ``.tex`` file names its bibliography via
  ``\\bibliography{refs}`` or ``\\addbibresource{refs.bib}``. We resolve that relative to
  the document and read it from disk, so the author never configures a path. Editing the
  ``.bib`` re-analyses every open ``.tex`` that references it.
* **Diagnostic routing.** Findings about the bibliography carry ``.bib`` offsets and must
  be published against the ``.bib`` URI, not the ``.tex``. :func:`_partition` splits them.
* **Two-phase publication.** ``didChange`` publishes instant diagnostics inline and hands
  the engine a callback that publishes again when background verification lands.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from . import __version__
from .compiling import default_gate
from .diagnostics import Code, Diagnostic
from .engine import AnalysisEngine
from .verification import get_default_searcher

SERVER_NAME = "aurelius-ide"
#: Never hardcode this. The client reports it in bug reports, and a version that disagrees
#: with the installed package sends you debugging the wrong build.
SERVER_VERSION = __version__

_BIB_DECL_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}")


#: A URI path component that starts with a drive letter, e.g. the `/D:/...` produced by
#: parsing `file:///D:/...` — the standard triple-slash form every real LSP client sends
#: for a Windows path (VS Code's `Uri.toString()` included).
_WINDOWS_DRIVE_RE = re.compile(r"^/[A-Za-z]:")


def _uri_to_path(uri: str) -> Path | None:
    """Invert :func:`_path_to_uri` — ``Path.as_uri()`` reversed.

    ``urlparse`` on ``file:///D:/foo`` yields the path component ``/D:/foo``, leading
    slash included. On Windows, handing that straight to ``Path()`` produces a *relative*
    path — ``WindowsPath('/D:/foo').is_absolute()`` is ``False`` — that resolves against
    the current drive rather than the file that was actually opened. Every caller of this
    function silently gets the wrong file: bibliography discovery finds nothing, the
    compile gate's sibling-staging step no-ops because the parent directory "doesn't
    exist". This was undetected because it only manifests with a real ``file://`` URI from
    an external client (VS Code, this repo's desktop prototype) — nothing in the test
    suite ever round-trips a hand-built URI string on Windows.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    raw = unquote(parsed.path)
    if _WINDOWS_DRIVE_RE.match(raw):
        raw = raw[1:]
    return Path(raw)


def _path_to_uri(path: Path) -> str:
    return path.as_uri()


def _to_lsp_diagnostic(d: Diagnostic) -> lsp.Diagnostic:
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=d.range.start.line, character=d.range.start.character),
            end=lsp.Position(line=d.range.end.line, character=d.range.end.character),
        ),
        message=d.message,
        severity=lsp.DiagnosticSeverity(int(d.severity)),
        code=d.code,
        source=SERVER_NAME,
        data=d.data,
    )


#: Codes whose ranges index into the .bib file rather than the .tex.
_BIB_CODES = frozenset({Code.UNUSED_BIB_ENTRY, Code.INCOMPLETE_BIB_ENTRY})


def _partition(diags: list[Diagnostic]) -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Split diagnostics into (tex-anchored, bib-anchored)."""
    tex = [d for d in diags if d.code not in _BIB_CODES]
    bib = [d for d in diags if d.code in _BIB_CODES]
    return tex, bib


class AureliusLanguageServer(LanguageServer):
    """Language server with an analysis engine and bibliography bookkeeping."""

    def __init__(self) -> None:
        super().__init__(name=SERVER_NAME, version=SERVER_VERSION)
        self.engine = AnalysisEngine(
            publish=self._publish_from_engine, on_progress=self._publish_progress
        )
        #: tex uri -> bib uri, so a .bib edit can re-run its dependents.
        self.bib_for: dict[str, str] = {}

    # -- bibliography resolution ---------------------------------------------------------

    def resolve_bib(self, tex_uri: str, tex_source: str) -> tuple[str, str | None]:
        """Find and read the bibliography referenced by a ``.tex`` document."""
        tex_path = _uri_to_path(tex_uri)
        if tex_path is None:
            return "", None
        match = _BIB_DECL_RE.search(tex_source)
        candidates: list[Path] = []
        if match:
            for name in match.group(1).split(","):
                name = name.strip()
                if not name:
                    continue
                filename = name if name.endswith(".bib") else name + ".bib"
                candidates.append(tex_path.parent / filename)
        # Fall back to any .bib sitting beside the paper — the common single-file case.
        candidates.extend(sorted(tex_path.parent.glob("*.bib")))

        for candidate in candidates:
            try:
                return candidate.read_text(encoding="utf-8"), _path_to_uri(candidate)
            except OSError:
                continue
        return "", None

    # -- publication ----------------------------------------------------------------------

    def _publish_from_engine(self, uri: str, diags: list[Diagnostic], version: int) -> None:
        """Callback invoked from the engine's background thread."""
        self.publish_split(uri, diags, version)

    def _publish_progress(self, uri: str, key: str, source: str, status: str) -> None:
        """A live 'checking OpenAlex...' step, sent the moment it happens.

        Custom notification, not `$/progress` — that protocol wants a token created via a
        `window/workDoneProgress/create` round trip per citation, which is more ceremony
        than a fire-and-forget UI ping needs. Not part of the four-command panel contract
        in ``client.ts`` either: this is a notification the client can simply ignore, not
        a request it must answer, so there is nothing to keep in sync if a client doesn't
        implement it.
        """
        self.protocol.notify(
            "aurelius/verificationProgress",
            {"uri": uri, "key": key, "source": source, "status": status},
        )

    def publish_split(self, tex_uri: str, diags: list[Diagnostic], version: int) -> None:
        tex_diags, bib_diags = _partition(diags)
        self.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(
                uri=tex_uri,
                version=version,
                diagnostics=[_to_lsp_diagnostic(d) for d in tex_diags],
            )
        )
        bib_uri = self.bib_for.get(tex_uri)
        if bib_uri:
            self.text_document_publish_diagnostics(
                lsp.PublishDiagnosticsParams(
                    uri=bib_uri,
                    diagnostics=[_to_lsp_diagnostic(d) for d in bib_diags],
                )
            )

    def analyze(self, uri: str, source: str, version: int) -> None:
        bib_text, bib_uri = self.resolve_bib(uri, source)
        if bib_uri:
            self.bib_for[uri] = bib_uri
        diags = self.engine.update(uri, source, version, bib_text, bib_uri)
        self.publish_split(uri, diags, version)


server = AureliusLanguageServer()


# --------------------------------------------------------------------------------------
# Document sync
# --------------------------------------------------------------------------------------


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: AureliusLanguageServer, params: lsp.DidOpenTextDocumentParams) -> None:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    if doc.uri.endswith(".bib"):
        _reanalyze_dependents(ls, doc.uri)
        return
    ls.analyze(doc.uri, doc.source, params.text_document.version or 0)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: AureliusLanguageServer, params: lsp.DidChangeTextDocumentParams) -> None:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    if doc.uri.endswith(".bib"):
        _reanalyze_dependents(ls, doc.uri)
        return
    ls.analyze(doc.uri, doc.source, params.text_document.version or 0)


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: AureliusLanguageServer, params: lsp.DidSaveTextDocumentParams) -> None:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    if not doc.uri.endswith(".bib"):
        ls.analyze(doc.uri, doc.source, 0)


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: AureliusLanguageServer, params: lsp.DidCloseTextDocumentParams) -> None:
    ls.engine.close(params.text_document.uri)


def _reanalyze_dependents(ls: AureliusLanguageServer, bib_uri: str) -> None:
    """A bibliography changed — re-run every open paper that cites it."""
    for tex_uri, mapped in list(ls.bib_for.items()):
        if mapped != bib_uri:
            continue
        try:
            doc = ls.workspace.get_text_document(tex_uri)
        except KeyError:
            continue
        ls.analyze(tex_uri, doc.source, doc.version or 0)


# --------------------------------------------------------------------------------------
# Hover — the "go to definition" of a citation
# --------------------------------------------------------------------------------------


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(ls: AureliusLanguageServer, params: lsp.HoverParams) -> lsp.Hover | None:
    """Show what a citation key actually resolves to, without leaving the editor."""
    uri = params.text_document.uri
    document = ls.engine.document(uri)
    if document is None:
        return None

    offset = _offset_of(document.text, params.position.line, params.position.character)
    ref = document.cite_ref_at(offset)
    if ref is None:
        return None

    entry = document.bib_entries.get(ref.key)
    if entry is None:
        return _markdown_hover(f"**`{ref.key}`**\n\nNo entry in the bibliography.")

    lines = [f"**{entry.title or ref.key}**", ""]
    if entry.author:
        lines.append(f"*{entry.author}*")
    facts = (entry.year, entry.fields.get("journal", ""), entry.entry_type)
    meta = " · ".join(x for x in facts if x)
    if meta:
        lines.append(meta)
    if entry.doi:
        lines.append(f"[doi:{entry.doi}](https://doi.org/{entry.doi})")

    # Attach the cached verification verdict if one exists. Never verify on hover — a
    # hover must be instant, and a blocking network call inside one is a hung editor.
    verdict = _cached_verdict(ls, entry)
    if verdict:
        icon = {"verified": "✓", "retracted": "⛔", "unverified": "⚠", "not_found": "✗"}.get(
            verdict.get("verdict", ""), "•"
        )
        lines += ["", "---", f"{icon} **{verdict.get('verdict', 'unknown')}** "
                  f"({verdict.get('confidence', '?')} confidence)"]
        if verdict.get("notes"):
            lines.append(f"\n{verdict['notes']}")

    return _markdown_hover("\n".join(lines))


def _cached_verdict(ls: AureliusLanguageServer, entry) -> dict | None:
    for analyzer in ls.engine.analyzers:
        if getattr(analyzer, "name", "") == "scholarly_verification":
            return analyzer.cache.get(analyzer.name, entry.content_hash())
    return None


def _markdown_hover(markdown: str) -> lsp.Hover:
    return lsp.Hover(
        contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=markdown)
    )


# --------------------------------------------------------------------------------------
# Code actions — one-click fixes
# --------------------------------------------------------------------------------------


@server.feature(
    lsp.TEXT_DOCUMENT_CODE_ACTION,
    lsp.CodeActionOptions(code_action_kinds=[lsp.CodeActionKind.QuickFix]),
)
def code_action(
    ls: AureliusLanguageServer, params: lsp.CodeActionParams
) -> list[lsp.CodeAction]:
    """Offer fixes: correct a mistyped key, or insert the verified BibTeX for a bad one."""
    actions: list[lsp.CodeAction] = []
    uri = params.text_document.uri

    for diag in params.context.diagnostics:
        data = diag.data or {}

        if diag.code == Code.UNDEFINED_CITATION and data.get("suggestion"):
            suggestion = data["suggestion"]
            actions.append(
                lsp.CodeAction(
                    title=f"Change to '{suggestion}'",
                    kind=lsp.CodeActionKind.QuickFix,
                    diagnostics=[diag],
                    edit=lsp.WorkspaceEdit(
                        changes={
                            uri: [lsp.TextEdit(range=diag.range, new_text=suggestion)]
                        }
                    ),
                )
            )

        # The range for AUR008 is exactly the offending '%', so escaping it is a
        # one-character replacement over the diagnostic's own range.
        if diag.code == Code.UNESCAPED_PERCENT:
            actions.append(
                lsp.CodeAction(
                    title="Escape as '\\%'",
                    kind=lsp.CodeActionKind.QuickFix,
                    diagnostics=[diag],
                    edit=lsp.WorkspaceEdit(
                        changes={uri: [lsp.TextEdit(range=diag.range, new_text="\\%")]}
                    ),
                )
            )

        # A binding mismatch spans "Smith et al.~\cite{key}", so the fix rewrites only
        # the key. Its offset inside that span is recomputed rather than stored, because
        # the buffer may have shifted since the diagnostic was published.
        if diag.code == Code.CITATION_BINDING and data.get("suggestion"):
            edit = _retarget_key_edit(ls, uri, diag, data["key"], data["suggestion"])
            if edit:
                actions.append(
                    lsp.CodeAction(
                        title=f"Cite '{data['suggestion']}' instead",
                        kind=lsp.CodeActionKind.QuickFix,
                        diagnostics=[diag],
                        edit=lsp.WorkspaceEdit(changes={uri: [edit]}),
                    )
                )

        if diag.code in (Code.UNVERIFIED_CITATION, Code.AUTHOR_MISMATCH) and data.get("bibtex"):
            bib_uri = ls.bib_for.get(uri)
            if bib_uri:
                actions.append(
                    lsp.CodeAction(
                        title="Append the verified BibTeX for the matched work",
                        kind=lsp.CodeActionKind.QuickFix,
                        diagnostics=[diag],
                        edit=lsp.WorkspaceEdit(
                            changes={
                                bib_uri: [
                                    lsp.TextEdit(
                                        range=_append_at(_line_count(ls, bib_uri)),
                                        new_text="\n" + data["bibtex"] + "\n",
                                    )
                                ]
                            }
                        ),
                    )
                )
    return actions


def _retarget_key_edit(
    ls: AureliusLanguageServer,
    uri: str,
    diag: lsp.Diagnostic,
    old_key: str,
    new_key: str,
) -> lsp.TextEdit | None:
    """Build an edit replacing ``old_key`` inside the diagnostic's range."""
    document = ls.engine.document(uri)
    if document is None:
        return None
    start = _offset_of(document.text, diag.range.start.line, diag.range.start.character)
    end = _offset_of(document.text, diag.range.end.line, diag.range.end.character)
    at = document.text.find(old_key, start, end)
    if at == -1:
        return None
    return lsp.TextEdit(
        range=lsp.Range(
            start=lsp.Position(*_line_char(document.text, at)),
            end=lsp.Position(*_line_char(document.text, at + len(old_key))),
        ),
        new_text=new_key,
    )


def _line_char(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset) + 1
    return line, offset - line_start


# --------------------------------------------------------------------------------------
# Compile gate — an explicit command, never part of the keystroke path
# --------------------------------------------------------------------------------------
#
# Every ``@server.command`` handler below takes its real parameters by name — ``uri``,
# ``query``, ``limit`` — rather than a single catch-all ``args`` list indexed by hand.
# That is not a style preference: pygls's ``workspace/executeCommand`` dispatcher inspects
# the handler's own signature and unpacks the client's JSON ``arguments`` array
# positionally, one element per declared parameter (after the injected ``ls``). A handler
# declared as ``def handler(ls, args)`` does not receive the array — pygls has already
# consumed its first (and, for a one-argument call, only) element to fill that single
# ``args`` slot. Every one of these five commands originally got this wrong, silently:
# ``uri = args[0]`` was indexing the *first character of the URI string*, and every real
# caller sending ``arguments: [uri]`` received "Only file:// documents can be compiled."
# for a perfectly valid URI. Nothing in the test suite caught it, because nothing had ever
# driven a command through pygls's actual dispatcher rather than calling the Python
# function directly — see ``tests/test_command_dispatch.py``, added once this surfaced.

COMPILE_GATE_COMMAND = "aurelius.compileGate"


@server.command(COMPILE_GATE_COMMAND)
def compile_gate(ls: AureliusLanguageServer, uri: str | None = None) -> dict[str, object]:
    """Run ``pdflatex``/``bibtex`` over a paper and publish what the toolchain said.

    Exposed as a command rather than an analyzer because a compile costs seconds and
    writes artefacts — running it on every keystroke would be both useless and hostile.
    The author asks for it at the moment they care, which is just before submitting.
    """
    if not uri:
        return {"ok": False, "reason": "No document URI supplied."}

    path = _uri_to_path(uri)
    if path is None:
        return {"ok": False, "reason": "Only file:// documents can be compiled."}

    try:
        source = ls.workspace.get_text_document(uri).source
    except KeyError:
        source = None

    bib_uri = ls.bib_for.get(uri)
    bib_path = _uri_to_path(bib_uri) if bib_uri else None

    gate = default_gate()
    if not gate.available():
        # Same rule as an unreachable index: say we could not check, never imply failure.
        return {"ok": False, "reason": "No LaTeX toolchain available.", "diagnostics": 0}

    diags = gate.check(path, bib_path=bib_path, source=source)
    instant = ls.engine.diagnostics(uri)
    ls.publish_split(uri, instant + diags, 0)
    return {"ok": True, "diagnostics": len(diags)}


COMPILE_PDF_COMMAND = "aurelius.compilePdf"


@server.command(COMPILE_PDF_COMMAND)
def compile_pdf(ls: AureliusLanguageServer, uri: str | None = None) -> dict[str, object]:
    """Compile the paper and persist the resulting PDF next to the source.

    A sibling to ``compileGate`` rather than a parameter added to it: that command's
    contract is "diagnostics about whether it built", and every existing caller expects
    exactly that response shape. This one exists for a different consumer — a PDF preview
    panel — that needs a real, addressable file. ``CompileGate.check`` always builds in a
    scratch directory it deletes before returning, so without ``pdf_output`` there would be
    nothing left on disk to point a viewer at by the time this function's caller sees the
    response.

    The PDF lands beside the ``.tex`` file as ``<stem>.pdf`` — the same place ``pdflatex``
    itself would put it without ``-output-directory`` — so it is exactly where an author
    already expects to find their compiled paper.
    """
    if not uri:
        return {"ok": False, "reason": "No document URI supplied."}

    path = _uri_to_path(uri)
    if path is None:
        return {"ok": False, "reason": "Only file:// documents can be compiled."}

    try:
        source = ls.workspace.get_text_document(uri).source
    except KeyError:
        source = None

    bib_uri = ls.bib_for.get(uri)
    bib_path = _uri_to_path(bib_uri) if bib_uri else None

    gate = default_gate()
    if not gate.available():
        # Same rule as an unreachable index: say we could not check, never imply failure.
        return {"ok": False, "reason": "No LaTeX toolchain available."}

    pdf_output = path.with_suffix(".pdf")
    diags, log = gate.check_with_log(path, bib_path=bib_path, source=source, pdf_output=pdf_output)
    instant = ls.engine.diagnostics(uri)
    ls.publish_split(uri, instant + diags, 0)

    errors = [d for d in diags if d.code == Code.COMPILE_ERROR]
    produced = pdf_output.is_file()
    return {
        "ok": True,
        "pdfPath": str(pdf_output) if produced else None,
        "pdfUri": _path_to_uri(pdf_output) if produced else None,
        # The real, complete transcript — a Debug Console shows this verbatim, distinct
        # from `diagnostics`, which is what parse_log distilled out of the same text.
        "log": log,
        "diagnostics": len(diags),
        "errors": len(errors),
    }


# --------------------------------------------------------------------------------------
# Panel commands — structured state for the editor UI
# --------------------------------------------------------------------------------------
#
# The panels need the *bibliography as a list of works with verdicts*, which is a
# different shape from a flat diagnostic stream. Rather than have the extension re-derive
# it by parsing diagnostic messages — brittle, and it would duplicate the parser in
# TypeScript — the server answers a question it can already answer cheaply from the
# document and the verification cache.

BIBLIOGRAPHY_COMMAND = "aurelius.bibliographyStatus"
SEARCH_COMMAND = "aurelius.searchLiterature"
SUBMISSION_GATE_COMMAND = "aurelius.submissionGate"

#: Cached-verdict lookup never triggers I/O. A panel refresh must not cost a round trip.
_VERDICT_ICON = {
    "verified": "verified",
    "retracted": "retracted",
    "not_found": "not_found",
    "unverified": "unverified",
}


@server.command(BIBLIOGRAPHY_COMMAND)
def bibliography_status(ls: AureliusLanguageServer, uri: str | None = None) -> dict[str, object]:
    """Every bibliography entry, with its cached verdict and where it is cited.

    Reads only what the engine already holds. An entry whose verification has not landed
    yet reports ``unchecked`` rather than a guess — the same rule as invariant 4, applied
    to a panel instead of a squiggle.

    Takes ``uri`` as its own named parameter, not a generic ``args`` list indexed by hand
    — see the comment above ``COMPILE_GATE_COMMAND`` for why that distinction is
    load-bearing rather than cosmetic.
    """
    document = ls.engine.document(uri) if uri else None
    if document is None:
        return {"ok": False, "reason": "No analysed document for that URI.", "entries": []}

    cited: dict[str, list[int]] = {}
    for ref in document.cite_refs:
        cited.setdefault(ref.key, []).append(document.range_of(ref.start, ref.end).start.line)

    entries = []
    for key, entry in sorted(document.bib_entries.items()):
        verdict = _cached_verdict(ls, entry) or {}
        entries.append(
            {
                "key": key,
                "title": entry.title,
                "author": entry.author,
                "year": entry.year,
                "doi": entry.doi,
                "venue": entry.fields.get("journal") or entry.fields.get("booktitle") or "",
                "entryType": entry.entry_type,
                "citedOnLines": sorted(cited.get(key, [])),
                "citeCount": len(cited.get(key, [])),
                "verdict": _VERDICT_ICON.get(str(verdict.get("verdict")), "unchecked"),
                "confidence": verdict.get("confidence") or "",
                "notes": verdict.get("notes") or "",
                "bibLine": document.bib_range_of(entry.start, entry.end).start.line,
            }
        )

    return {
        "ok": True,
        "entries": entries,
        "bibUri": document.bib_uri or "",
        "counts": _tally(entries),
    }


def _tally(entries: list[dict[str, object]]) -> dict[str, int]:
    counts = {"total": len(entries), "retracted": 0, "not_found": 0, "unverified": 0,
              "verified": 0, "unchecked": 0, "uncited": 0}
    for e in entries:
        counts[str(e["verdict"])] = counts.get(str(e["verdict"]), 0) + 1
        if not e["citeCount"]:
            counts["uncited"] += 1
    return counts


@server.command(SEARCH_COMMAND)
def search_literature(
    ls: AureliusLanguageServer, query: str = "", limit: int = 8
) -> dict[str, object]:
    """Search scholarly indexes and return insertable BibTeX for each hit.

    Failure returns ``ok: False`` with a reason rather than an empty result list, so the
    editor can say "search is unreachable" instead of the far more alarming "no such
    paper exists" — the same distinction the verifier draws.
    """
    if not str(query).strip():
        return {"ok": True, "results": []}

    try:
        results = get_default_searcher().search(str(query), limit=limit)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"Could not reach the literature index ({type(exc).__name__}).",
            "results": [],
        }
    return {"ok": True, "results": results}


@server.command(SUBMISSION_GATE_COMMAND)
def submission_gate(ls: AureliusLanguageServer, uri: str | None = None) -> dict[str, object]:
    """Everything that must hold before a paper is submitted, as a pass/fail checklist.

    Combines the live analysis with a real compile. Each check reports ``pass``, ``fail``
    or ``skip`` — never a silent success — because a gate that cannot run a check must say
    so rather than let it read as satisfied.
    """
    if not uri:
        return {"ok": False, "reason": "No document URI supplied."}

    document = ls.engine.document(uri)
    diagnostics = ls.engine.diagnostics(uri)
    by_code: dict[str, int] = {}
    for d in diagnostics:
        by_code[d.code] = by_code.get(d.code, 0) + 1

    checks: list[dict[str, object]] = [
        _check(
            "No unresolved citation keys",
            by_code.get(Code.UNDEFINED_CITATION, 0),
            blocking=True,
        ),
        _check("No retracted citations", by_code.get(Code.RETRACTED_CITATION, 0), blocking=True),
        _check(
            "Every reference resolves to a real work",
            by_code.get(Code.UNVERIFIED_CITATION, 0),
            blocking=True,
        ),
        _check("Prose matches the works it cites", by_code.get(Code.CITATION_BINDING, 0)),
        _check("Bibliography entries are complete", by_code.get(Code.INCOMPLETE_BIB_ENTRY, 0)),
        _check("Empirical claims carry a source", by_code.get(Code.UNCITED_CLAIM, 0)),
        _check("No unescaped percent signs", by_code.get(Code.UNESCAPED_PERCENT, 0)),
    ]

    gate = default_gate()
    path = _uri_to_path(uri)
    if not gate.available() or path is None:
        checks.append(
            {
                "label": "The paper compiles",
                "status": "skip",
                "count": 0,
                "blocking": True,
                "detail": "No LaTeX toolchain found — this check did not run.",
            }
        )
    else:
        source = None
        try:
            source = ls.workspace.get_text_document(uri).source
        except KeyError:
            pass
        bib_uri = ls.bib_for.get(uri)
        compile_diags = gate.check(
            path, bib_path=_uri_to_path(bib_uri) if bib_uri else None, source=source
        )
        errors = [d for d in compile_diags if d.code == Code.COMPILE_ERROR]
        checks.append(_check("The paper compiles", len(errors), blocking=True))
        checks.append(
            _check(
                "No undefined cross-references",
                len([d for d in compile_diags if d.code == Code.COMPILE_WARNING]),
            )
        )
        ls.publish_split(uri, diagnostics + compile_diags, 0)

    blocking = [c for c in checks if c["blocking"] and c["status"] == "fail"]
    skipped = [c for c in checks if c["status"] == "skip"]
    return {
        "ok": True,
        "checks": checks,
        "blocking": len(blocking),
        "skipped": len(skipped),
        # "ready" requires every blocking check to have actually run and passed. A skipped
        # check is not a passed one, so it withholds the verdict rather than granting it.
        "ready": not blocking and not skipped,
        "references": len(document.bib_entries) if document else 0,
    }


def _check(label: str, count: int, blocking: bool = False) -> dict[str, object]:
    return {
        "label": label,
        "status": "pass" if count == 0 else "fail",
        "count": count,
        "blocking": blocking,
        "detail": "",
    }


def _append_at(line: int) -> lsp.Range:
    """An empty range at the start of ``line`` — an insertion point, not a replacement."""
    position = lsp.Position(line=line, character=0)
    return lsp.Range(start=position, end=position)


def _line_count(ls: AureliusLanguageServer, uri: str) -> int:
    try:
        return len(ls.workspace.get_text_document(uri).source.splitlines())
    except (KeyError, AttributeError):
        return 0


def _offset_of(text: str, line: int, character: int) -> int:
    offset = 0
    for i, content in enumerate(text.splitlines(keepends=True)):
        if i == line:
            return offset + character
        offset += len(content)
    return offset


def main() -> None:
    """Entry point for ``aurelius-lsp`` — speaks LSP over stdio."""
    server.start_io()


if __name__ == "__main__":
    main()
