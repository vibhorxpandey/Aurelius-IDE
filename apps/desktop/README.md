# Aurelius Desktop — prototype

A VS Code–shaped desktop shell for Aurelius: activity bar, file explorer, tabs, a Monaco
editor, a Problems panel, and dedicated Bibliography and Submission Gate panels — wired to
the **real** `aurelius-lsp` language server, not mocked data.

## What this is, and isn't

This is the prototype named in the roadmap's kill-gates
([the plan](../../CHANGELOG.md) treats it as pre-Gate-2 exploration, not a committed path):
a fast way to see the vision — "one place to take a paper from a blank file to
submission" — as a real, running application, before spending the 12-16 weeks a
production desktop shell costs.

**It is explicitly not:**
- The Stage 11 fork of Code - OSS. That is a different, much larger undertaking — see
  `ARCHITECTURE.md` in the repository root and the roadmap's Gate 2 ("name a feature
  impossible as a VS Code extension, or don't fork").
- Signed, packaged, or auto-updating. There is no installer here.
- A replacement for the VS Code extension in `editors/vscode/` — that remains the
  supported way to use Aurelius in an existing editor.

**It is real** where it matters: the language server is spawned as a genuine child
process (`python -m aurelius_ide.lsp`), JSON-RPC is framed and relayed over Electron IPC
by hand (`src/main/lspServer.ts`) rather than mocked, and every diagnostic, hover, and
bibliography verdict on screen comes from the actual analysis engine running against the
actual demo paper in `demo-workspace/`.

## Run it

```bash
cd apps/desktop
npm install
npm run dev
```

Requires a Python environment with `aurelius-ide[lsp]` installed (`pip install -e
".[lsp]"` from the repository root) — the app looks for `python`, `python3`, then `py` on
PATH and runs the server as a module, so no console-script PATH issues.

Opens with `demo-workspace/paper.tex`, which carries the same intentional errors used
throughout this project's docs and tests: an undefined citation key, an uncited claim, and
prose with no source. Diagnostics appear as you type; they are not staged.

## Architecture, briefly

```
src/main/           Electron main process: window, LSP process spawn + JSON-RPC framing,
                     filesystem IPC. Owns everything Node-privileged.
src/preload/         contextBridge surface — the only thing the renderer can reach.
src/renderer/src/
  lsp/client.ts       ~150-line hand-rolled LSP client over the IPC transport. Not
                       monaco-languageclient — that wants a WebSocket, and this app
                       already owns the child process, so the transport is IPC.
  editor/             Model registry (one persistent Monaco instance, models swap on tab
                       change — losing scroll position on every click is not acceptable)
                       and diagnostic-to-marker conversion.
  monaco/languages.ts  Monaco ships no LaTeX/BibTeX language; these are hand-written
                       Monarch tokenizers, not full grammars.
  components/          The shell: ActivityBar, Explorer, TabBar, EditorPane, StatusBar,
                       ProblemsPanel, BibliographyPanel, GatePanel.
  platform.ts          Detects whether a preload bridge exists. Outside Electron (e.g. a
                       browser pointed at the Vite dev server) the shell still renders
                       with static content, clearly labelled — real operations refuse
                       rather than fake a result.
```

## Known gaps, honestly

Same discipline as the rest of this project — say what's missing rather than paper over
it:

- **No file watching.** Editing `paper.tex` outside the app won't be picked up.
- **No code actions / quick fixes.** The server implements them
  (`aurelius_ide/lsp.py::code_action`); this prototype's editor doesn't call
  `textDocument/codeAction` yet, unlike the VS Code extension, which does.
- **One workspace at a time**, and it must be opened via folder path — no multi-root, no
  recent-workspaces list.
- **No settings UI.** Nothing here reads `aurelius.claims.enabled` or
  `aurelius.debounceMs` — same gap the roadmap already tracks for the extension.
- **No unsaved-changes prompt on close.** Closing a dirty tab discards the buffer; the
  file on disk is untouched, but in-editor changes are lost silently.
