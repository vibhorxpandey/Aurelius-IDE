# Aurelius for VS Code

Live citation verification, retraction checking, and a submission gate for LaTeX papers.

Your editor already tells you when a symbol doesn't resolve. This tells you when a
citation doesn't.

## What you get

**Inline diagnostics** as you type — unresolved keys, uncited claims, prose that credits
the wrong author, an unescaped `%` silently eating half a line. Structural checks are
instant; scholarly verification lands a moment later, the same split a code IDE makes
between parse errors and type errors.

**A bibliography panel** listing every reference with its live verdict, sorted by severity
so a retracted paper is never below the fold:

```
AURELIUS · BIBLIOGRAPHY                    ⟳  🔍
  ⛔ chen2019      RETRACTED
  ✗  kumar2021    not in any index
  ⚠  liu2020      unverified
  ○  park2018     unchecked
  ✓  smith2020    verified · 3×
  ✓  ghosh2020    verified · uncited
```

**Find a paper and cite it** — <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd> searches
OpenAlex, inserts `\cite{key}` at the cursor and appends the BibTeX entry to your `.bib`.
The entry comes from the index rather than from memory, so the key, authors and year are
right by construction. Retracted hits are shown, labelled, and require confirmation.

**A submission gate** that compiles the paper (`pdflatex` → `bibtex` → `pdflatex` ×2) and
reports a checklist. A check that could not run reports `skip`, and a skipped blocking
check yields **INCONCLUSIVE**, never *ready* — the gate will not imply it checked
something it couldn't.

## Prerequisites

The extension is a thin client; the analysis is a Python language server.

```bash
pip install "aurelius-ide[all] @ git+https://github.com/vibhorxpandey/Aurelius-IDE"
```

Confirm `aurelius-lsp` is on your PATH, or set `aurelius.pythonPath` to the interpreter
that has it installed.

Literature search works with no extras and no API key — it queries OpenAlex directly over
the standard library. The `verify` extra adds Crossref, arXiv and Semantic Scholar for
citation verification.

## Commands

| Command | Default binding |
|---|---|
| Aurelius: Find a Paper and Cite It | <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd> |
| Aurelius: Run Submission Gate | — |
| Aurelius: Compile and Report Errors | — |
| Aurelius: Refresh Bibliography | — |
| Aurelius: Restart Language Server | — |

## Settings

| Setting | Default | Purpose |
|---|---|---|
| `aurelius.serverPath` | `aurelius-lsp` | Executable to launch |
| `aurelius.pythonPath` | `""` | Interpreter to run `-m aurelius_ide.lsp` with |
| `aurelius.claims.enabled` | `true` | Flag uncited empirical claims |
| `aurelius.verification.enabled` | `true` | Check citations against scholarly indexes |
| `aurelius.debounceMs` | `700` | Quiet period before background verification |

## Develop

```bash
npm install
npm run compile
npm run package     # builds a .vsix
```

Then press <kbd>F5</kbd> to launch an Extension Development Host and open a `.tex` file
with a sibling `.bib`.

The client is deliberately thin: `client.ts` is the only module that talks to the server,
and the four commands it calls (`aurelius.bibliographyStatus`, `aurelius.searchLiterature`,
`aurelius.submissionGate`, `aurelius.compileGate`) are declared in `aurelius_ide/lsp.py`.
Panels ask the server for structured state rather than re-parsing diagnostic messages,
which would mean maintaining a second copy of the parser in TypeScript.

## Not published yet

This is not on the Marketplace or Open VSX. Install the packaged `.vsix` with
**Extensions → … → Install from VSIX**, or `code --install-extension aurelius-ide-0.2.0.vsix`.
