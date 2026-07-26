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
pytest                            # full suite (~1s, no network)
pytest tests/test_engine.py -q    # one module
ruff check src tests              # lint
aurelius-lsp                      # run the language server on stdio
```

The suite needs no network *and no TeX installation* — `tests/test_compiling.py` replays
captured `pdflatex` logs through a stub runner.

Tests must stay hermetic and fast. Nothing in `tests/` may touch the network — use
`StubVerifier` from `tests/conftest.py`.

## Architecture

```
document.py      LaTeX + BibTeX → structured spans. Pure parsing, no I/O.
diagnostics.py   Diagnostic/Severity/Code. Mirrors LSP shape without importing pygls.
cache.py         Content-addressed TTL cache, memory + disk.
verification.py  Verifier protocol + backends. The ONLY module that knows about the network.
compiling.py     The compile gate. Runs pdflatex/bibtex; parses logs into diagnostics.
engine.py        Scheduling: two-phase analysis, debouncing, version guarding.
analyzers/       Pure functions: document → [Diagnostic].
  citations.py     AUR001-005: undefined keys, unused/incomplete entries, verification.
  claims.py        AUR006: empirical assertions with no source.
  syntax.py        AUR008: an unescaped % that eats the rest of the line.
  binding.py       AUR009: prose that names a source the cited entry contradicts.
lsp.py           pygls transport. Contains no analysis logic.
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

## Not built yet

- VS Code extension is scaffolded in `editors/vscode/` but not published. It does not yet
  surface the `aurelius.compileGate` command.
- Claim-to-source binding is *partial*. `AUR009` catches prose that contradicts the entry
  it cites — the wrong-key case. It cannot tell whether a work genuinely supports the
  assertion, so a sentence citing a real, correctly-named, topically unrelated paper still
  passes. That needs semantics the stdlib parser cannot supply.
## House style, settled

`UP006`/`UP007`/`UP035` are in `[tool.ruff.lint] ignore`. The codebase uses the `typing`
spelling (`List[str]`, `Optional[X]`) with `from __future__ import annotations` in every
module; those rules ask for the builtin spelling. Both are correct on Python 3.10+ — what
matters is picking one, and the code had already picked. Match the surrounding style
rather than reintroducing the mix. `ruff check src tests` is green; keep it that way.
