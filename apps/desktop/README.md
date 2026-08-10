# Aurelius Desktop — prototype

A VS Code–shaped desktop shell for Aurelius: activity bar, file explorer, tabs, a Monaco
editor, a Problems panel, an integrated terminal, and dedicated Bibliography, Submission
Gate, Diagrams, Agent Activity, and Extensions panels — wired to the **real**
`aurelius-lsp` language server, not mocked data.

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
prose with no source. Diagnostics appear as you type; they are not staged. A local profile
gate (name only, no password — see below) runs once per machine before the workspace opens.

## The additions, and what's real about each

| Feature | What's real | What isn't |
|---|---|---|
| **Login** | A local display identity, stored in `localStorage`. Personalises the workspace, the profile panel, and the profile icon docked at the bottom of the activity bar (VS Code puts Accounts there). | Not authentication — no password, no backend, no third-party sign-in. Said so on the screen itself. |
| **Right profile panel** | Every number is read off the same diagnostics state the rest of the app renders from — files open, errors, warnings, files analyzed. No separate stats source to drift out of sync. | — |
| **Terminal** | A genuine shell process (`cmd.exe` / `$SHELL`), spawned by the main process, streaming real stdout/stderr. Run `ls`, `git status`, `python --version` — they actually execute. | Not a full PTY (no `node-pty`, to avoid a native-compilation dependency). Line-buffered with local echo, not real terminal semantics — arrow-key history and full-screen programs (vim, htop) don't work. |
| **Agent Activity** | Every entry is derived from an actual `publishDiagnostics` batch, status change, gate run, or compile the client received. "Structural" vs. "verification" pass is read off which diagnostic codes are present (AUR002/003/004 are network-only) — the real two-phase split from `ARCHITECTURE.md` § 4, made visible. | — |
| **Architecture & Diagrams** | Live Mermaid rendering (`mermaid.render`, sandboxed via `securityLevel: "strict"`) of `.mmd` files, source and preview updating together. `demo-workspace/architecture.mmd` diagrams Aurelius's own real module layout. | — |
| **Extensions** | 4 built-in tools (Bibliography, Submission Gate, Diagrams, Agent Activity) — these are the real panels above, just also listed here. | 123 marketplace entries are catalogue data (`data/extensions.ts`) for a populated-looking view — nothing installs or runs. Said so in the panel's own doc comment. |
| **Live search progress** | The Agent Activity panel shows each citation's real OpenAlex → Crossref → arXiv → Semantic Scholar cascade as it happens (`aurelius/verificationProgress`, a fire-and-forget notification from `aurelius_ide.engine`) — not a staged animation. A source the cascade never reaches, because an earlier one already matched, simply never lights up. | Google Scholar isn't in the cascade: it has no public API and blocks scraping, so nothing here queries it — the panel shows the four sources that are genuinely checked. |
| **Run and Debug → compiled paper** | "Run" invokes the real `aurelius.compilePdf` LSP command, which shells out to an actual LaTeX toolchain (`pdflatex`/`bibtex`, or `tectonic` — see `compiling.py::default_gate`) against the file on disk. The toolchain's own stdout/stderr lands verbatim in the Debug Console. On success the produced PDF opens in a source/PDF split view, rendered by `pdf.js` from the real bytes on disk — not an image or a canned preview — with a working Download button (`dialog.showSaveDialog` + a real file copy). | If no LaTeX toolchain is on `PATH` (and no `AURELIUS_LATEX`/`AURELIUS_TECTONIC` override), the panel reports that honestly rather than staging a result — see invariant 7 in the root `CLAUDE.md`. |
| **New File / New Folder** | Explorer toolbar icons create real filesystem entries via IPC (`workspace:create-file`, `workspace:create-folder`, both refusing to overwrite) and re-list the directory from disk afterward — not a client-side tree mutation. | No rename or delete from the Explorer yet. |
| **Debug Console** | A third tab alongside Problems and Terminal in the bottom panel, showing the exact compiler transcript from the most recent `aurelius.compilePdf` run. | Only populated by compiles — it isn't a general stdout sink. |

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
  monaco/languages.ts  Monaco ships no LaTeX/BibTeX/Mermaid language; these are
                       hand-written Monarch tokenizers, not full grammars.
  state/               profile.ts (local identity), activity.ts (the live event log).
  components/          ActivityBar, Explorer, TabBar, EditorPane, StatusBar,
                       ProblemsPanel (hosts Problems, Debug Console, and Terminal),
                       BibliographyPanel, GatePanel, DiagramsPanel, MermaidPreview,
                       RunAndDebugPanel, PdfPreview, AgentActivityPanel, ExtensionsView,
                       LoginScreen, ProfilePanel.
  platform.ts          Detects whether a preload bridge exists. Outside Electron (e.g. a
                       browser pointed at the Vite dev server) the shell still renders
                       with static content, clearly labelled — real operations refuse
                       rather than fake a result.
src/main/terminalProcess.ts  Spawns the real shell for the integrated terminal.
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
- **`pdfjs-dist` is pinned to `4.10.38`, not latest.** 6.x calls brand-new TypedArray/Map
  built-ins (`Uint8Array.prototype.toHex`, `Map.prototype.getOrInsertComputed`) with no
  feature-detection, and Electron 33's bundled Chromium 130 predates all of them — every
  compiled PDF failed to render until this was pinned back to a version that targets the
  browser generation this Electron actually ships.
