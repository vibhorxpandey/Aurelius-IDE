# Aurelius IDE

**A language server for research papers.** Live citation verification and claim analysis
for LaTeX, in your editor.

Write a paper the way you write code: undefined citation keys are unresolved symbols,
references that don't resolve to real works are type errors, and empirical claims with no
source are lint warnings. You find out while you write, not when a reviewer does.

```
paper.tex
  14:1   warning  AUR006  Uncited quantitative claim.
  19:22  warning  AUR008  Unescaped '%' — LaTeX drops the rest of this line.
  27:47  error    AUR001  Undefined citation key 'ghost2030' — did you mean 'ghosh2020'?
  29:3   warning  AUR009  Prose says Smith et al. but 'jones2021' is Jones (2021).
  31:12  error    AUR003  'chen2019' cites a RETRACTED work.
references.bib
  23:1   hint     AUR005  'orphaned2020' is never cited in the document.
```

## Install

Not yet on PyPI. Install from the repository:

```bash
pip install "aurelius-ide[all] @ git+https://github.com/vibhorxpandey/Aurelius-IDE"
```

The analysis engine has **no dependencies**. Extras are opt-in:

| Extra | Adds | Needed for |
|---|---|---|
| `lsp` | `pygls` | Running the language server |
| `verify` | [`aurelius-mcp`](https://github.com/vibhorxpandey/Aurelius) | Checking citations against scholarly indexes |
| `all` | both | Normal editor use |

Without `verify` you get structural analysis — undefined keys, malformed entries, uncited
claims. That still works offline and in CI.

### Relationship to Aurelius (the MCP server)

[**Aurelius**](https://github.com/vibhorxpandey/Aurelius) is the sibling project: a
fact-checked research MCP server that gives Claude, Cursor, or Gemini CLI a set of
verification tools, and drives the *screen → draft → fact-check → revise* loop from chat.

Same checks, different surface. Aurelius answers *"is this citation real?"* when a model
asks it. Aurelius-IDE answers the same question **inline in your editor, while you type**,
against a paper you are writing by hand. This package uses `aurelius-mcp` as its
verification backend when it's installed, and degrades to structural analysis when it
isn't — see [invariant 1](CLAUDE.md) and `verification.py`.

## Use

**In an editor.** Point your LSP client at `aurelius-lsp` (stdio) for `latex` and `bibtex`
files. A VS Code extension is scaffolded in `editors/vscode/`.

**In CI, or a pre-submission gate:**

```python
from aurelius_ide import AnalysisEngine, Severity

engine = AnalysisEngine()
diagnostics = engine.analyze_now(
    "file:///paper.tex",
    open("paper.tex").read(),
    bib_text=open("references.bib").read(),
)

errors = [d for d in diagnostics if d.severity is Severity.ERROR]
if errors:
    raise SystemExit(f"{len(errors)} blocking issues before submission")
```

## Diagnostics

| Code | Severity | Meaning |
|---|---|---|
| `AUR001` | error | Citation key with no bibliography entry |
| `AUR002` | error / warning | **error** when no index has the work at all; **warning** when it was found but could not be confirmed |
| `AUR003` | error | Cited work has been **retracted** |
| `AUR004` | warning | Title matched but the authors differ |
| `AUR005` | hint | Bibliography entry nothing cites |
| `AUR006` | warning | Empirical claim with no source |
| `AUR007` | warning | Entry missing fields its type requires |
| `AUR008` | warning | Unescaped `%` that silently comments out the rest of a line |
| `AUR009` | warning | Prose names an author or year the cited entry contradicts |
| `AUR010` | error | The paper does not compile |
| `AUR011` | warning | Compile warning — undefined reference, stale cross-references |

`AUR010` and `AUR011` come from the [compile gate](#the-compile-gate) and only appear when
you ask for it. Everything else runs continuously as you type.

## The compile gate

The checks above read your source. None of them can tell you the paper *builds* — and
that is where the expensive failures live: a reference that renders as `[?]`, a missing
figure, a stray `\end{itemize}`. All of them survive a clean lint; none survive a reviewer.

So the gate runs the real toolchain — `pdflatex`, `bibtex`, `pdflatex` twice more, because
cross-reference numbers are only trustworthy after the third pass — and reports what it
said as ordinary diagnostics.

```python
from aurelius_ide import CompileGate, DockerRunner

gate = CompileGate(runner=DockerRunner(image="texlive/texlive:TL2024"))
problems = gate.check("paper.tex", bib_path="references.bib")
```

`CompileGate()` uses a local TeX installation; `DockerRunner` pins one for reproducibility,
with networking disabled. `default_gate()` picks between them from
`AURELIUS_LATEX_DOCKER_IMAGE` and `AURELIUS_LATEX`, so the same CI config works on a
runner with TeX Live and on one with only Docker.

This is a gate, not an analyzer. A compile costs seconds and writes artefacts, so it never
runs on the keystroke path — call it from CI, a pre-submission hook, or the
`aurelius.compileGate` editor command. Building in a scratch directory keeps your folder
free of `.aux` files, and **no toolchain means no diagnostics**: "we could not check" is
never reported as "your paper is broken".

## How it stays fast

Verifying a reference costs a few HTTP round trips. Doing that per keystroke over a
60-reference bibliography is obviously impossible, so three things happen instead.

**Analysis runs in two phases.** Structural checks are pure string work over an
already-parsed document — about 1.4ms for a full paper — so they run synchronously as you
type. Scholarly verification runs on a debounced background thread and publishes a second
round when it lands. Same split a code IDE makes between parse errors and type errors.

**Results are content-addressed.** The cache keys on a hash of each bibliography entry's
semantic fields, not on the document. Editing prose can't invalidate a verification
result, because the entry didn't change. Reindenting your `.bib` doesn't either.

**Background passes are version-guarded.** A verification that returns after the document
has moved on is discarded rather than published against text that no longer exists.

## Design notes

**Inconclusive is not a finding.** If the network is unreachable, citations report as
*unchecked*, not *not found*. Telling an author on a plane that their entire bibliography
is fabricated is the worst false positive this tool could produce, and it's the one a
naive implementation makes by default.

**Under-report rather than over-report.** The claim analyzer ignores sentences reporting
your own results, figure and section cross-references, and numbers in Methods. It misses
some real claims. That's the right trade: a linter that cries wolf gets switched off, and
a switched-off linter catches nothing.

The same rule shapes the two source-level checks. `AUR008` only flags a `%` written
directly against a digit (`45%`), so `x = 5 % a real comment` stays quiet and `45 %` with a
space goes unreported. `AUR009` only fires when the prose *names* a source — `Smith et al.`
or a parenthetical year — because a bare `\cite` after a capitalised word asserts nothing
for the bibliography to contradict, and guessing which capitalised words are surnames is
exactly how the check would start crying wolf.

**Binding is checked where the author wrote it down twice.** `Smith et al. (2019) showed
X \cite{jones2021}` has an immaculate bibliography and still credits the wrong paper.
Deciding whether a work genuinely *supports* a claim needs semantics this tool doesn't
have; deciding whether prose and key name the same work is string comparison, and it
catches the stale-key edit that produces most real instances.

**Verification is swappable.** Everything depends on the `Verifier` protocol, not on a
specific backend. Bring a licensed index, or a stub for tests.

## Contributing

See [CLAUDE.md](CLAUDE.md) for architecture, invariants, and how to add an analyzer.

```bash
pip install -e ".[dev,lsp]"
pytest          # 152 tests, ~1s, no network, no TeX installation
ruff check src tests
```

## License

MIT
