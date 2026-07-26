# Aurelius for VS Code

Live citation verification and claim analysis for LaTeX papers.

## Prerequisites

```bash
pip install "aurelius-ide[all]"
```

Confirm `aurelius-lsp` is on your PATH, or set `aurelius.pythonPath` to the interpreter
that has it installed.

## Develop

```bash
npm install
npm run compile
```

Then press <kbd>F5</kbd> in VS Code to launch an Extension Development Host, and open a
`.tex` file with a sibling `.bib`.

## Settings

| Setting | Default | Purpose |
|---|---|---|
| `aurelius.serverPath` | `aurelius-lsp` | Executable to launch |
| `aurelius.pythonPath` | `""` | Interpreter to run `-m aurelius_ide.lsp` with |
| `aurelius.claims.enabled` | `true` | Flag uncited empirical claims |
| `aurelius.verification.enabled` | `true` | Check citations against scholarly indexes |
| `aurelius.debounceMs` | `700` | Quiet period before background verification |
