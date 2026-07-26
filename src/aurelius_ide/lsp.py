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
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from .compiling import default_gate
from .diagnostics import Code, Diagnostic
from .engine import AnalysisEngine

SERVER_NAME = "aurelius-ide"
SERVER_VERSION = "0.1.0"

_BIB_DECL_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}")


def _uri_to_path(uri: str) -> Optional[Path]:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


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


def _partition(diags: List[Diagnostic]) -> Tuple[List[Diagnostic], List[Diagnostic]]:
    """Split diagnostics into (tex-anchored, bib-anchored)."""
    tex = [d for d in diags if d.code not in _BIB_CODES]
    bib = [d for d in diags if d.code in _BIB_CODES]
    return tex, bib


class AureliusLanguageServer(LanguageServer):
    """Language server with an analysis engine and bibliography bookkeeping."""

    def __init__(self) -> None:
        super().__init__(name=SERVER_NAME, version=SERVER_VERSION)
        self.engine = AnalysisEngine(publish=self._publish_from_engine)
        #: tex uri -> bib uri, so a .bib edit can re-run its dependents.
        self.bib_for: Dict[str, str] = {}

    # -- bibliography resolution ---------------------------------------------------------

    def resolve_bib(self, tex_uri: str, tex_source: str) -> Tuple[str, Optional[str]]:
        """Find and read the bibliography referenced by a ``.tex`` document."""
        tex_path = _uri_to_path(tex_uri)
        if tex_path is None:
            return "", None
        match = _BIB_DECL_RE.search(tex_source)
        candidates: List[Path] = []
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

    def _publish_from_engine(self, uri: str, diags: List[Diagnostic], version: int) -> None:
        """Callback invoked from the engine's background thread."""
        self.publish_split(uri, diags, version)

    def publish_split(self, tex_uri: str, diags: List[Diagnostic], version: int) -> None:
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
def hover(ls: AureliusLanguageServer, params: lsp.HoverParams) -> Optional[lsp.Hover]:
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


def _cached_verdict(ls: AureliusLanguageServer, entry) -> Optional[dict]:
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
) -> List[lsp.CodeAction]:
    """Offer fixes: correct a mistyped key, or insert the verified BibTeX for a bad one."""
    actions: List[lsp.CodeAction] = []
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
) -> Optional[lsp.TextEdit]:
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


def _line_char(text: str, offset: int) -> Tuple[int, int]:
    line = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset) + 1
    return line, offset - line_start


# --------------------------------------------------------------------------------------
# Compile gate — an explicit command, never part of the keystroke path
# --------------------------------------------------------------------------------------

COMPILE_GATE_COMMAND = "aurelius.compileGate"


@server.command(COMPILE_GATE_COMMAND)
def compile_gate(ls: AureliusLanguageServer, args) -> Dict[str, object]:
    """Run ``pdflatex``/``bibtex`` over a paper and publish what the toolchain said.

    Exposed as a command rather than an analyzer because a compile costs seconds and
    writes artefacts — running it on every keystroke would be both useless and hostile.
    The author asks for it at the moment they care, which is just before submitting.
    """
    uri = args[0] if args else None
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
