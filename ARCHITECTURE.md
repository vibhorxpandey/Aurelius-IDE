# Architecture

How Aurelius is put together, and why it is put together that way.

This describes the system **as it is today**, not as it is planned. Where something is
absent, it says so — the [Known limitations](#known-limitations) section at the end is as
load-bearing as the rest of the document.

---

## 1. What this is

A language server that treats a research paper like source code. You open a `.tex` file and
get live diagnostics on the line you are writing: citation keys with no bibliography entry,
references that resolve to nothing in any scholarly index, papers that were retracted after
you cited them, prose that credits one author while citing another, empirical claims with no
source at all.

The mental model is a code IDE throughout, and it is not a metaphor — it determines the
scheduling, the caching, and the error handling:

| Code IDE | Here |
|---|---|
| Unresolved symbol | `\cite{key}` with no BibTeX entry |
| Type error | Citation that doesn't resolve to a real work |
| Linter warning | Empirical claim with no source |
| Go-to-definition | Hover a key → the resolved work |
| Quick fix | Correct a mistyped key, insert verified BibTeX |
| Parse errors vs. type errors | Structural pass vs. network pass |
| Build failure | The paper does not compile |

**Size, for orientation:** 3,472 lines of Python across 15 modules, 836 lines of TypeScript
across 5, and 175 tests that run in about 1.5 seconds with no network and no TeX installation.

---

## 2. Layers

```
                       ┌──────────────────────────────┐
   editors/vscode/     │  extension.ts                │  activation, commands, status bar
   (TypeScript)        │  client.ts ◄─── the only     │  LSP client + the 4 command names
                       │  bibliographyView.ts   module│  tree views
                       │  gateView.ts      that talks │
                       │  literatureSearch.ts to the  │
                       └────────────┬───────── server ┘
                                    │  LSP over stdio
   ═════════════════════════════════╪═══════════════════════ process boundary
                                    │
                       ┌────────────▼─────────────────┐
                       │  lsp.py                      │  transport only, no analysis
                       └────────────┬─────────────────┘
                                    │
                       ┌────────────▼─────────────────┐
                       │  engine.py                   │  scheduling, debounce, version guard
                       └────────────┬─────────────────┘
                                    │
                       ┌────────────▼─────────────────┐
                       │  analyzers/                  │  document → [Diagnostic], pure
                       └────────────┬─────────────────┘
                                    │
          ┌─────────────┬───────────┼───────────┬──────────────┐
          ▼             ▼           ▼           ▼              ▼
      document.py  diagnostics.py cache.py verification.py  config.py
      parsing      the finding    memoise  THE NETWORK      paths
                   types                   BOUNDARY

      compiling.py ── deliberately outside the pipeline; see §6
```

**Dependency direction is strictly downward.** `analyzers/` imports from `document`,
`diagnostics`, `cache` and `verification` — never from `engine` or `lsp`. The reason is not
tidiness: it is what lets the whole analysis stack run headless in CI, in a web backend, or
from a notebook, with `pygls` not installed at all.

---

## 3. Module reference

| Module | Lines | Responsibility |
|---|---|---|
| `document.py` | 589 | LaTeX + BibTeX → structured spans. Pure parsing, no I/O. |
| `lsp.py` | 633 | pygls transport, bibliography discovery, panel commands. No analysis. |
| `compiling.py` | 453 | The compile gate: runs the TeX toolchain, parses logs. |
| `verification.py` | 365 | `Verifier` + `Searcher` protocols and backends. The network boundary. |
| `engine.py` | 279 | Two-phase scheduling, debouncing, version guarding, stats. |
| `analyzers/binding.py` | 283 | AUR009 — prose that contradicts the entry it cites. |
| `analyzers/citations.py` | 252 | AUR001–005 — the four citation checks. |
| `analyzers/claims.py` | 138 | AUR006 — empirical assertions with no source. |
| `cache.py` | 114 | Content-addressed TTL cache, memory + disk. |
| `analyzers/syntax.py` | 109 | AUR008 — an unescaped `%` that eats the rest of a line. |
| `diagnostics.py` | 80 | `Severity`, `Code`, `Diagnostic`. Mirrors LSP without importing it. |
| `__init__.py` | 68 | Public API — 27 exported names. |
| `analyzers/base.py` | 42 | `Analyzer` protocol and `BaseAnalyzer`. |
| `analyzers/__init__.py` | 35 | `DEFAULT_ANALYZERS` — the registration list. |
| `config.py` | 32 | Cache directory resolution. |

### `document.py` — the parser

Stdlib only. No TeX parser dependency, because a full LaTeX grammar is undecidable in the
general case (macros can redefine syntax) — but the constructs that matter here (`\cite`
family, sectioning, math regions, comments, verbatim) are lexically regular in every real
paper. We parse those exactly and ignore the rest rather than pretending to understand the
whole document.

Key types: `PositionIndex` (offset → line/character in O(log n)), `CiteKeyRef`, `BibEntry`,
`Sentence`, `Section`, `ResearchDocument`.

**Offsets are first-class.** Every parsed element carries a byte-offset span *and* an
LSP-style range, because diagnostics must point at exact ranges in an editor.

### `engine.py` — the scheduler

Owns open documents, decides what to recompute, and gets results to the editor fast enough
to feel live. See §4.

### `analyzers/` — the checks

Six analyzers, registered in `DEFAULT_ANALYZERS`. Each is a pure function from a parsed
document to a list of diagnostics; the engine cares about exactly one extra property,
`is_network`, which decides which pass it runs in.

---

## 4. The two-phase analysis model

Verifying one reference costs one to four HTTP round trips. Doing that per keystroke over a
60-entry bibliography is not possible. Three mechanisms make live analysis viable.

**Two phases.** Structural analyzers are pure string work over an already-parsed document —
about 1.4 ms for a full paper — so they run synchronously on every keystroke and publish
immediately. Network analyzers run on a debounced background thread and publish a second,
superset round when they land. The author sees an undefined key the moment they type it and
learns the reference is fabricated a second later. Same split a code IDE makes between parse
errors and type errors.

**Content-addressed caching.** The cache keys on a hash of each bibliography entry's
*semantic* fields — title, author, year, DOI, journal — not on the document. Editing prose
cannot invalidate a verification result, because the entry did not change. Reindenting a
`.bib` costs nothing. In practice a warm cache means only genuinely new or edited references
reach the network.

**Version guarding.** A background pass carries the document version it started from and
re-checks it after returning from I/O. If the document moved on, the result is dropped rather
than published against text that no longer exists. Without it, diagnostics underline the
wrong words — the stale-result race every language server has to solve.

```
keystroke ──► parse ──► instant pass ──► publish              (~1.4 ms)
                 │
                 └────► debounce 700 ms ──► network pass ──► version still current?
                                                              ├─ yes → publish superset
                                                              └─ no  → drop
```

---

## 5. The network boundary

`verification.py` is the **only** module that reaches the network, in either direction — to
*check* a citation the author already wrote, and to *find* one they haven't. Both live in one
file so that "what does this tool talk to?" has a single answer, auditable by reading it.

Two protocols, four backends:

| Protocol | Backend | Notes |
|---|---|---|
| `Verifier` | `AureliusVerifier` | Lazily imports `aurelius-mcp`; OpenAlex → Crossref → arXiv → Semantic Scholar |
| `Verifier` | `NullVerifier` | Used when `aurelius-mcp` is absent. Always inconclusive. |
| `Searcher` | `OpenAlexSearcher` | Keyless, stdlib `urllib`, works with no extras installed |
| `Searcher` | `NullSearcher` | Raises rather than returning empty |

### Inconclusive is never a finding

This is the most important rule in the codebase and it is a correctness fix, not a nicety.

The naive implementation reports a network failure as `not_found`, which renders in the editor
as *every reference in your bibliography is fabricated*. That is the single worst possible
false positive for a tool whose entire pitch is research integrity: it is alarming, it is
wrong, and it appears exactly when the user is on a plane and least able to check.

So `VerdictKind.ERROR` is deliberately distinct from `NOT_FOUND` — the first means *we do not
know*, the second means *we asked and the answer was no*. Only the second is a finding.
`_diagnostic_for()` returns `None` for anything inconclusive, and `AureliusVerifier` goes
further: it downgrades a suspicious `not_found` to `ERROR` when a connectivity probe says the
machine is offline.

`Searcher` draws the same line differently: an empty list means *nothing found*, while an
unreachable index **raises**, so the caller can tell them apart and say "index unreachable"
rather than "no such paper."

---

## 6. The compile gate

`compiling.py` runs the real toolchain — `pdflatex` → `bibtex` → `pdflatex` ×2 — and turns
its logs into ordinary `Diagnostic` objects. Three LaTeX passes, because cross-reference
numbers land in the `.aux` on one pass and are read back on the next, so undefined-reference
warnings are only trustworthy after the third.

**It is deliberately not an analyzer.** `BaseAnalyzer` promises a pure function of a parsed
document, and the engine's two phases are "instant" and "network". A compile is neither: it
costs seconds, it needs a real file rather than an editor buffer, and it writes artefacts.
Wiring it into the keystroke path would mean recompiling a document while it is being typed.
It is a gate — called from CI, or the `aurelius.compileGate` command.

**The runner is injected** (`CompileRunner` protocol) for the same reason the verifier is:
tests must not require a TeX installation. `SubprocessRunner` uses a local distribution,
`DockerRunner` pins one for reproducibility with networking disabled, `UnavailableRunner`
stands in when there is none.

**A toolchain that cannot run reports nothing.** `CompileGate.check()` returns `[]` when the
runner is unavailable — the same logic as §5. *No TeX installed* must never render as *your
paper does not build*.

---

## 7. Diagnostic catalogue

Codes are a public contract. Editor settings and CI gates key off them, so renaming one is a
breaking change.

| Code | Severity | Meaning | Emitted by | Anchored in |
|---|---|---|---|---|
| `AUR001` | error | Citation key with no bibliography entry | `citations.py` | `.tex` |
| `AUR002` | error / warning / info | No index has this work (error); found but unconfirmed (warning); verified at medium confidence (info) | `citations.py` | `.tex` |
| `AUR003` | error | Cited work has been **retracted** | `citations.py` | `.tex` |
| `AUR004` | warning | Title matched but the authors differ | `citations.py` | `.tex` |
| `AUR005` | hint | Bibliography entry nothing cites | `citations.py` | **`.bib`** |
| `AUR006` | warning | Empirical claim with no source | `claims.py` | `.tex` |
| `AUR007` | warning | Entry missing fields its type requires | `citations.py` | **`.bib`** |
| `AUR008` | warning | Unescaped `%` silently commenting out a line | `syntax.py` | `.tex` |
| `AUR009` | warning | Prose credits an author or year the entry contradicts | `binding.py` | `.tex` |
| `AUR010` | error | The paper does not compile | `compiling.py` | `.tex` |
| `AUR011` | warning | Undefined cross-reference, stale labels, BibTeX warning | `compiling.py` | `.tex` |

`AUR005` and `AUR007` carry offsets into the `.bib` file, not the `.tex`. They are routed to
the `.bib` URI by `_partition()` in `lsp.py`. See invariant 3 — and note that this routing is
currently done *by diagnostic code*, which is a known structural limitation (§10).

### Two analyzers deliberately under-report

`AUR006` ignores sentences reporting the author's own results, figure and section
cross-references, and numbers in Methods. `AUR008` only fires on a `%` written directly
against a digit, so `x = 5 % a real comment` stays quiet. `AUR009` only fires when the prose
*names* a source (`et al.` or a parenthetical year).

All three miss real instances. That is the correct trade: a linter that cries wolf gets
switched off, and a switched-off linter catches nothing.

---

## 8. The cross-language contract

The extension is thin on purpose. `client.ts` is the only TypeScript module that talks to the
server, and the panels ask for **structured state** rather than re-deriving it by parsing
diagnostic messages — which would mean a second copy of the parser in TypeScript that drifts
the first time a message is reworded.

Four command names are shared across the process boundary:

| Command | Declared in `lsp.py` | Consumed in `client.ts` | Returns |
|---|---|---|---|
| `aurelius.bibliographyStatus` | `BIBLIOGRAPHY_COMMAND` | `COMMANDS.bibliography` | entries + verdicts + counts |
| `aurelius.searchLiterature` | `SEARCH_COMMAND` | `COMMANDS.search` | candidate works + BibTeX |
| `aurelius.submissionGate` | `SUBMISSION_GATE_COMMAND` | `COMMANDS.submissionGate` | pass/fail/skip checklist |
| `aurelius.compileGate` | `COMPILE_GATE_COMMAND` | `COMMANDS.compileGate` | ok + diagnostic count |

**Nothing catches a mismatch at compile time.** Renaming one means editing both files
together. The TypeScript response types in `client.ts` (`BibEntryStatus`, `GateResult`, …) are
hand-mirrored from the Python dicts and have the same property.

---

## 9. Invariants

Eight rules that must not be broken. Each exists because breaking it caused, or would cause, a
silent failure.

1. **The engine is stdlib-only.** `pygls` is imported exclusively in `lsp.py`, behind the
   `lsp` extra. `aurelius-mcp` is imported exclusively in `verification.py`, lazily, inside a
   try/except. A third-party import anywhere else breaks headless and CI use.

2. **Masking preserves offsets.** `_mask_regions` replaces comments, math and verbatim with
   *spaces of identical length*. It must never delete characters — every offset computed
   against masked text indexes the original document, and shortening it silently misaligns
   every diagnostic range.

3. **Bibliography ranges use `bib_range_of`, not `range_of`.** `BibEntry` offsets index the
   `.bib`. Mapping them through the `.tex` position index yields plausible but wrong line
   numbers, and it fails silently.

4. **Inconclusive is not a finding.** See §5.

5. **Cache keys hash semantic fields only.** Reindenting a `.bib` must not re-verify the
   bibliography.

6. **Network passes are version-guarded.** `_network_pass` re-checks `doc.version` after I/O.
   Removing that check reintroduces the stale-diagnostic race.

7. **The compile gate is never on the keystroke path.** See §6.

8. **`DEFAULT_ANALYZERS` is the single source of truth.** The engine builds its analyzer list
   from that tuple via `_instantiate`. It once kept a hardcoded second copy, which meant
   following the documented registration step registered nothing. `tests/test_registration.py`
   pins the two together.

---

## 10. Known limitations

Stated plainly, because the roadmap only makes sense against an honest baseline.

**The unit of work is one `.tex` plus one sibling `.bib`.** There is no project model: no
`\input`/`\include` resolution, no root-document concept, no multi-`.bib` support, no
workspace folders. A real paper with `sections/` and `figures/` is not handled — and
`compiling.py::_stage_siblings` flat-copies siblings into the build directory, so
subdirectories break.

**Six LSP features are implemented**: `didOpen`, `didChange`, `didSave`, `didClose`, `hover`,
`codeAction`. Not implemented: completion, definition, references, document symbols, workspace
symbols, formatting, semantic tokens, rename, folding ranges, inlay hints, code lens, pull
diagnostics, `didChangeConfiguration`, progress reporting.

**Three contributed settings do nothing.** `aurelius.claims.enabled`,
`aurelius.verification.enabled` and `aurelius.debounceMs` are declared in the extension but
there is no `didChangeConfiguration` handler, and `AnalysisEngine` has no analyzer-enablement
mechanism to hang one on.

**Diagnostics are routed to files by diagnostic code**, not by a URI on the diagnostic itself
(`_partition` in `lsp.py`). This works for exactly one `.tex` and one `.bib` and cannot survive
a project model.

**No PDF viewer and no SyncTeX.** `pdflatex` is invoked without `-synctex=1`, and the produced
PDF lands in a temp directory that is deleted immediately unless `keep_artifacts=True`.

**TeX detection uses `shutil.which`**, which fails inside a macOS GUI app because it does not
inherit the shell `PATH`. A MacTeX user launching from Finder is told no toolchain exists.

**`_probe_network` imports `httpx`, which is not a declared dependency of any extra.** Without
it the probe silently fails and a genuine `not_found` is downgraded to `ERROR` — suppressing a
true finding.

**Claim-to-source binding is partial.** `AUR009` catches prose contradicting the entry it
cites — the wrong-key case. It cannot tell whether a work genuinely *supports* an assertion,
so a sentence citing a real, correctly-named, topically unrelated paper still passes.

**Nothing is published.** Not on PyPI, not on the VS Code Marketplace, not on Open VSX. CI runs
on Ubuntu only and has no build, release or publish job; the test suite has never run on
Windows or macOS.

---

## 11. A packaging constraint worth knowing

The desktop app will ship an embedded Python runtime. That is only cheap while every bundled
dependency is pure Python — one set of files works on every OS and architecture, with no
manylinux, universal2 or musl variants to build and test.

Measured, not assumed:

| Install | Closure | Pure? |
|---|---|---|
| `.[lsp]` | pygls, lsprotocol, cattrs, attrs, typing-extensions | **yes** |
| `.[verify]` | + aurelius-mcp → pydantic-core, cryptography, cffi, rpds-py, pywin32 | **no** — compiled Rust and C |

So the bundle ships the **`lsp` extra only**. That is not a compromise: without `verify`,
structural analysis, literature search (`OpenAlexSearcher` is stdlib `urllib`) and the compile
gate all still work, and scholarly verification degrades to `NullVerifier`, which reports
inconclusive and emits nothing — per §5. Users wanting the full four-index chain install
`aurelius-mcp` into their own Python.

`scripts/check_pure_python.py` enforces this in CI, per platform. If `verify` ever has to be
bundled, the answer is running `aurelius-mcp` **out of process**, not adding compiled wheels
to the embedded runtime.

## 12. Testing

175 tests, ~1.5 seconds, **no network and no TeX installation required**. That is a hard
constraint, not a nice property — it is what lets CI prove the engine works with verification
unavailable, which is the degraded mode most users will first experience.

| Boundary | How it is stubbed |
|---|---|
| Scholarly verification | `StubVerifier` in `conftest.py`, injected via `set_default_verifier()` |
| Literature search | `urllib.request.urlopen` monkeypatched with a captured OpenAlex payload |
| The TeX toolchain | A stub `CompileRunner` replaying captured `pdflatex` log text |

Every analyzer has **negative tests**, and there are usually more of them than positive ones.
The sentences a linter must *not* flag matter more than the ones it must.
