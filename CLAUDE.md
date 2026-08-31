# CLAUDE.md

Context for Claude Code working in this repository.

## What this is

A language server that treats a research paper like source code. Open a `.tex` file and
get live diagnostics: undefined citation keys, references that don't resolve to real
works, retracted citations, and uncited empirical claims.

The mental model throughout is a code IDE:

| Code IDE | Here |
|---|---|
| Unresolved symbol | `\cite{key}` with no BibTeX entry |
| Type error | Citation that doesn't resolve to a real work |
| Linter warning | Empirical claim with no source |
| Go-to-definition | Hover a key → the resolved work |
| Quick fix | Correct a mistyped key, insert verified BibTeX |

## Commands

```bash
pip install -e ".[dev,lsp]"       # editable install with test + LSP deps
pytest                            # full suite (~1.5s, no network)
pytest tests/test_engine.py -q    # one module
ruff check src tests scripts      # lint
aurelius-lsp                      # run the language server on stdio
```

Four gates run in CI. Run them before pushing — each one exists because the thing it checks
already broke silently once:

```bash
python scripts/sync_version.py --check        # one version, four derived files
python scripts/check_command_contract.py      # lsp.py and client.ts agree on command names
python scripts/check_pure_python.py           # the bundled extra stays pure Python
python scripts/sync_version.py                # regenerate release-manifest.json
```

**The version lives in exactly one place**: `__version__` in `src/aurelius_ide/__init__.py`.
`pyproject.toml` reads it via hatchling, `lsp.py` imports it, and `sync_version.py` pushes it
into the extension manifest and `release-manifest.json`. Never edit a version anywhere else.

The suite needs no network *and no TeX installation* — `tests/test_compiling.py` replays
captured `pdflatex` logs through a stub runner.

Tests must stay hermetic and fast. Nothing in `tests/` may touch the network — use
`StubVerifier` from `tests/conftest.py`.

## Architecture

[ARCHITECTURE.md](ARCHITECTURE.md) is the full treatment — layers, the two-phase model, the
network boundary, the diagnostic catalogue, and what is *not* built. This is the summary.

```
document.py      LaTeX + BibTeX → structured spans. Pure parsing, no I/O.
diagnostics.py   Diagnostic/Severity/Code. Mirrors LSP shape without importing pygls.
cache.py         Content-addressed TTL cache, memory + disk.
verification.py  Verifier + Searcher protocols and backends. The ONLY module that touches
                 the network — both directions, so "what does this talk to?" has one answer.
compiling.py     The compile gate. Runs pdflatex/bibtex; parses logs into diagnostics.
engine.py        Scheduling: two-phase analysis, debouncing, version guarding.
analyzers/       Pure functions: document → [Diagnostic].
  citations.py     AUR001-005: undefined keys, unused/incomplete entries, verification.
  claims.py        AUR006: empirical assertions with no source.
  syntax.py        AUR008: an unescaped % that eats the rest of the line.
  binding.py       AUR009: prose that names a source the cited entry contradicts.
lsp.py           pygls transport + the panel commands. Contains no analysis logic.
editors/vscode/  The extension. Thin client; see "The editor surface" below.
```

Dependency direction is strictly downward. `analyzers/` imports from `document`,
`diagnostics`, `cache`, `verification` — never from `engine` or `lsp`.

`compiling.py` sits outside the analyzer pipeline on purpose — see invariant 7.

## Invariants — do not break these

**1. The engine is stdlib-only.** `pygls` is imported exclusively in `lsp.py` and lives
behind the `lsp` extra. `aurelius-mcp` is imported exclusively in `verification.py`,
lazily, inside a try/except. Adding a third-party import anywhere else breaks headless
and CI use.

**2. Masking preserves offsets.** `_mask_regions` in `document.py` replaces comments,
math, and verbatim regions with *spaces of identical length*. It must never delete
characters — every offset computed against masked text is used to index the original
document, and shortening it silently misaligns every diagnostic range.

**3. Bibliography ranges use `bib_range_of`, not `range_of`.** `BibEntry` offsets index
the `.bib` file. Mapping them through the `.tex` position index produces plausible but
wrong line numbers, and it fails silently. Diagnostics carrying `Code.UNUSED_BIB_ENTRY`
or `Code.INCOMPLETE_BIB_ENTRY` are routed to the `.bib` URI by `_partition` in `lsp.py`.

**4. Inconclusive is not a finding.** A verifier that cannot reach an index returns
`VerdictKind.ERROR`, and `_diagnostic_for` returns `None` for it. Never report "citation
not found" when the real cause was a network failure — that renders as *your entire
bibliography is fabricated* and is the worst false positive this tool can produce.

**5. Cache keys hash semantic fields only.** `BibEntry.content_hash` covers title,
author, year, doi, journal, and so on — not formatting. Reindenting a `.bib` file must
not trigger re-verification of the whole bibliography.

**6. Network passes are version-guarded.** `_network_pass` re-checks `doc.version` after
returning from I/O and drops results if the document moved on. Removing that check
reintroduces the stale-diagnostic race.

**7. The compile gate is never on the keystroke path.** `compiling.py` deliberately does
not subclass `BaseAnalyzer` and is not in `DEFAULT_ANALYZERS`. A compile costs seconds,
needs a real file rather than an editor buffer, and writes artefacts. It is invoked
explicitly — from CI, or the `aurelius.compileGate` command. Its "cannot run the
toolchain" case returns `[]`, for the same reason as invariant 4: *no TeX installed* must
never render as *your paper does not build*.

**8. `DEFAULT_ANALYZERS` is the single source of truth.** `AnalysisEngine` builds its
analyzer list from that tuple via `_instantiate`, handing the shared cache to any analyzer
whose `__init__` accepts one. It used to keep a hardcoded second copy, which meant
following the registration step below silently registered nothing. `tests/test_registration.py`
pins the two together.

## Adding an analyzer

1. Subclass `BaseAnalyzer` in `analyzers/`, set `name` and `is_network`.
2. Implement `run(doc) -> List[Diagnostic]`. Pure — no I/O unless `is_network = True`.
3. Add a stable code to `diagnostics.Code`. Codes are a public contract: editor settings
   and CI gates key off them, so renaming one is a breaking change.
4. Register it in `analyzers/__init__.py::DEFAULT_ANALYZERS`.
5. Test both directions. **Every analyzer needs negative tests** — the sentences it must
   *not* flag matter more than the ones it must. A linter that cries wolf gets disabled,
   and a disabled linter catches nothing.

## Gotchas

* **An unescaped `%` in LaTeX is a comment.** `45%` silently truncates the line. This is
  correct behaviour and there's a test asserting it. Fixtures must use `45\%` — except in
  `tests/test_syntax.py`, where the bare form is the thing under test.
* **`syntax.py` reads `doc.text`, not the masked view.** It is the one analyzer that must,
  because masking blanks comments and the offending `%` *is* the comment. It re-derives
  comment boundaries itself and consults `doc.literal_spans` to stay out of verbatim
  environments and percent-encoded URLs.
* **`\citep[see][p.~4]{key}`** — optional args come before the key group. The regex in
  `document.py` handles arbitrarily many; don't simplify it.
* **BibTeX braces protect capitalisation.** `{BERT}` is stripped during parsing because
  the consumer matches against index titles, where the braces would never appear.
* **`pygls` 2.x** uses `from pygls.lsp.server import LanguageServer`. The 1.x path
  (`pygls.server`) does not exist in 2.x.
* Sentence spans are trimmed of surrounding whitespace. Without that, a diagnostic's
  range starts at the previous sentence's terminator and underlines the wrong line.

## Style

Standard library first. Type hints on public functions. Docstrings explain *why* a design
choice was made, not what the code does — the non-obvious reasoning is the part worth
writing down. Comments on the counterintuitive parts only.

## The editor surface

`editors/vscode/` is a working extension (v0.2.0), packaged but **not published** to the
Marketplace or Open VSX. It contributes a bibliography panel, a submission-gate panel, and
literature search bound to <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd>.

The client is thin on purpose. `client.ts` is the only module that talks to the server,
and panels ask for **structured state** via four of the five `@server.command` handlers in
`lsp.py` —
`bibliographyStatus`, `searchLiterature`, `submissionGate`, `compileGate`. They do not
re-derive state by parsing diagnostic messages, which would mean a second copy of the
parser in TypeScript that drifts the first time a message is reworded.

Those command name constants are a cross-language contract. Renaming one means editing
`lsp.py` and `client.ts` together; nothing catches a mismatch at compile time.

## Not built yet

See [ARCHITECTURE.md § Known limitations](ARCHITECTURE.md#10-known-limitations) for the full,
honest list — no project model, six LSP features, three settings that do nothing, no PDF
viewer, nothing published. That section is the baseline the roadmap is measured against, so
keep it accurate.

[ROADMAP.md](ROADMAP.md) has the longer-term direction: a Verifier API, a machine-checkable
research-artifact protocol, and a regulated-research audit-trail layer, all built on the
verification engine that already exists here.

- Claim-to-source binding is *partial*. `AUR009` catches prose that contradicts the entry
  it cites — the wrong-key case. It cannot tell whether a work genuinely supports the
  assertion, so a sentence citing a real, correctly-named, topically unrelated paper still
  passes. That needs semantics the stdlib parser cannot supply.

## House style, settled

Annotations use the **builtin** spelling — `list[str]`, `dict[str, X]`, `X | None` — not
`typing.List` / `Optional`. Every module keeps `from __future__ import annotations`. Only
`Any`, `Protocol`, and `runtime_checkable` still come from `typing`, because they have no
builtin equivalent. There is no `ignore` list in the ruff config; keep it that way.

**Pin ruff, and run the pinned version.** `dev` pins `ruff>=0.16,<0.17`. Import grouping
and the `UP` rules move between releases: an older local ruff reported this tree clean
while CI's newer one found 40 errors in it. `[tool.ruff.lint.isort] known-first-party` is
set for the same reason — without it, grouping depends on whether `aurelius_ide` happens
to be installed in the environment doing the checking.
