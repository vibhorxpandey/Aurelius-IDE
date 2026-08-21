# Changelog

Notable changes to Aurelius. Format follows [Keep a Changelog](https://keepachangelog.com);
versioning follows the policy below.

## Versioning policy

**The Python package and the VS Code extension share one version and ship together.**
`__version__` in `src/aurelius_ide/__init__.py` is canonical; everything else is derived by
`scripts/sync_version.py`, and CI fails if they drift.

While the major version is `0`, the minor is treated as the breaking-change slot:

| Change | Bump |
|---|---|
| Removing or renaming a diagnostic code (`AUR0xx`) | minor |
| Removing or renaming an LSP command | minor |
| Changing the shape of a command's response | minor |
| Removing a public export from `aurelius_ide` | minor |
| Dropping a Python version | minor |
| New diagnostic code, new command, new analyzer | minor |
| New quick fix, better message, wider detection | patch |
| Fixing a false positive or false negative | patch |

**Diagnostic codes are a public contract.** Editor settings and CI gates key off them, so a
rename is a breaking change even though nothing fails to compile.

---

## [Unreleased]

## [0.4.0] — unreleased

### Added

- **`npm install aurelius-ide`.** A root-level `package.json` publishes this project to
  npm as a thin bootstrapper: its `postinstall` (`scripts/postinstall.js`) detects a
  Python 3.10+ interpreter and runs `pip install aurelius-ide[all]` under the hood, then
  falls back to installing straight from this repository's tag if the pinned version
  isn't on PyPI yet. It does not reimplement anything — the language server is still
  pure Python; this just gives npm-first users and tooling a familiar install path. The
  package's version is kept in lockstep with `__version__` by `sync_version.py`, same as
  the VS Code extension.
- **Real PyPI and npm publishing in the release workflow.** `.github/workflows/release.yml`
  now has `pypi` (via `pypa/gh-action-pypi-publish`, OIDC trusted publishing, no stored
  secret) and `npm` (via a repo-scoped `NPM_TOKEN`) jobs, gated to real tag pushes only.
  Both still need one-time manual account setup outside this repo before they'll
  succeed — see the comment at the top of `release.yml`.
- **Live, per-source verification progress.** `AnalysisEngine` takes an `on_progress`
  callback — `(uri, key, source, status)`, fired as each citation is actually checked
  against OpenAlex, Crossref, arXiv, and Semantic Scholar in that real cascade order (the
  same order `aurelius-mcp`'s `verify_citation` uses internally, now exposed via its new
  `on_step` parameter — `aurelius-mcp>=0.7.0`). `status` is `"checking"`, then `"hit"` or
  `"miss"`; a source the cascade never reaches because an earlier one already matched is
  simply never reported. A cache hit reports nothing at all — nothing was actually queried,
  and staging a fake cascade for an instant result would contradict the reason this
  project reports `ERROR` instead of guessing (invariant 4). Version-guarded like every
  other network result: a step from a pass superseded by a newer edit is dropped rather
  than painted over text that no longer exists.
- **`aurelius/verificationProgress` notification.** `lsp.py` forwards `on_progress` over
  the wire as a fire-and-forget custom notification (not `$/progress` — that protocol's
  per-token `create` handshake is more ceremony than a UI ping needs). Not part of the
  four-command panel contract: a client that ignores it loses nothing.
- `ScholarlyVerificationAnalyzer.set_progress(callback)` — thread-local, because the
  engine runs each open document's network pass on its own `threading.Timer` thread, and
  a shared attribute would let one document's progress bleed into another's.

## [0.3.2] — unreleased

### Fixed

- **All four panel commands, and the new `compilePdf`, silently misread their arguments —
  every real client call to them failed or crashed.** pygls's `workspace/executeCommand`
  dispatcher inspects a `@server.command` handler's own signature and unpacks the client's
  JSON `arguments` array *positionally, one element per declared parameter* (after the
  injected `ls`). Every handler here was written as `def handler(ls, args)` and then did
  `uri = args[0]` — but for a one-argument call, pygls had already consumed that single
  array element to fill the lone `args` parameter, so `args` was bound to the URI *string
  itself* and `args[0]` was its first character. `bibliographyStatus`, `submissionGate`,
  `compileGate` all returned `"Only file:// documents can be compiled"` for a perfectly
  valid URI; `searchLiterature`, which expects two arguments, raised `TypeError` outright,
  since pygls's own leftover-argument check rejects a call that didn't consume the whole
  array.

  Fixed by declaring each handler's real parameters (`uri`, or `query` and `limit`) instead
  of a generic `args` list indexed by hand. `tests/test_command_dispatch.py` closes the gap
  that let this go undetected: every earlier test called these functions directly as plain
  Python, which bypasses pygls's dispatch entirely and cannot see this class of bug. The new
  tests drive the same argument-unpacking pygls itself runs. Found and confirmed via a full
  protocol-level run against the real server — all five commands now verified working
  end-to-end, including a real compiled PDF and real OpenAlex search results.

### Added

- **`aurelius.compilePdf`** — compiles the paper and persists the resulting PDF next to the
  source (`<stem>.pdf`, the same place `pdflatex` itself would put it), for panels that need
  a real, addressable file rather than a verdict about a scratch directory that no longer
  exists by the time the response arrives. `CompileGate.check()` gained a `pdf_output`
  parameter to support this; existing callers are unaffected (default `None`, unchanged
  behaviour).
- **`TectonicRunner`** — a `CompileRunner` for [Tectonic](https://tectonic-typesetting.github.io),
  a single self-contained binary that resolves its own TeX packages on demand instead of
  needing a multi-gigabyte TeX Live install. `default_gate()` now falls back to it
  automatically when `pdflatex` isn't on `PATH`; override with `AURELIUS_TECTONIC`.

## [0.3.1] — unreleased

### Fixed

- **Bibliography resolution was silently broken on Windows for every real LSP client.**
  `_uri_to_path` parsed the standard triple-slash Windows file URI (`file:///D:/...` — the
  form VS Code, and any other real client, actually sends) into a path that
  `.is_absolute()` reports as `False`. Every citation in every paper looked undefined,
  because `resolve_bib`'s sibling-`.bib` glob and its explicit-declaration lookup both
  resolve against `tex_path.parent`, which was silently the wrong directory. The compile
  gate's sibling-file staging degraded the same way — no error, just files quietly not
  found.

  Found by building a second real LSP client (a desktop prototype, `apps/desktop/`) and
  running it against real Windows paths — the first place in this project's history a raw
  `file://` URI built by an external client was round-tripped through `_uri_to_path` and
  actually checked. `Path.as_uri()`, the reverse direction, was always correct; only the
  URI-to-path direction was broken, which is why nothing caught it: every existing test
  only ever builds a URI *from* a path, never parses one *back*. `tests/test_lsp.py` closes
  that gap.

## [0.3.0] — unreleased

First version intended for release. `0.1.0` and `0.2.0` existed only in the repository and
were never published to PyPI, the VS Code Marketplace, or Open VSX.

### Added

- **Language server** with eleven diagnostics: unresolved citation keys (`AUR001`), references
  in no scholarly index (`AUR002`), retracted work (`AUR003`), author mismatches (`AUR004`),
  uncited bibliography entries (`AUR005`), empirical claims with no source (`AUR006`),
  incomplete entries (`AUR007`), unescaped `%` that silently comments out a line (`AUR008`),
  prose that credits an author the cited entry contradicts (`AUR009`), and build failures
  (`AUR010`/`AUR011`).
- **Two-phase analysis** — structural checks run synchronously (~1.4 ms for a full paper),
  scholarly verification runs debounced on a background thread and publishes a second round.
- **Content-addressed caching** on each entry's semantic fields, so editing prose cannot
  invalidate a verification result and reindenting a `.bib` costs nothing.
- **Compile gate** — `pdflatex` → `bibtex` → `pdflatex` ×2, with local and Docker runners.
- **Literature search** against OpenAlex — keyless, standard library only, no extras required.
  Returns insertable BibTeX with brace-protected titles.
- **VS Code extension**: bibliography panel with live verdicts sorted by severity, submission
  gate panel, find-and-cite on <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>C</kbd>, hover to resolve a
  key, and four quick fixes.
- `ARCHITECTURE.md` documenting the layers, the network boundary, the diagnostic catalogue,
  the invariants, and an honest list of what is not built.
- `scripts/sync_version.py` and `release-manifest.json` — one canonical version, verified in CI.

### Changed

- Annotations moved to the builtin spelling (`list[str]`, `X | None`). No ruff `ignore` list.
- `ruff` pinned to `>=0.16,<0.17` with `known-first-party` set: an older local ruff reported
  the tree clean while CI's newer one found 40 errors in the same source.

### Fixed

- `AnalysisEngine` built its analyzer list from a hardcoded copy rather than
  `DEFAULT_ANALYZERS`, so following the documented registration step registered nothing.
  `tests/test_registration.py` now pins the two together.
- `AureliusVerifier` computed whether an exception was a transport failure and then discarded
  the result. The distinction now survives in the note, so "you are offline" and "the verifier
  is broken" read differently.

### Known limitations

Carried deliberately into this release; see
[ARCHITECTURE.md § 10](ARCHITECTURE.md#10-known-limitations).

- The unit of work is one `.tex` plus one sibling `.bib`. No `\input` resolution, no project
  model, no multi-`.bib`.
- Six LSP features implemented. No completion, definition, references, or document symbols.
- `aurelius.claims.enabled`, `aurelius.verification.enabled` and `aurelius.debounceMs` are
  contributed by the extension but not yet consumed by the server.
- No PDF viewer and no SyncTeX.
- TeX detection uses `shutil.which`, which fails inside a macOS GUI app because it does not
  inherit the shell `PATH`.
- `_probe_network` imports `httpx`, which is not a declared dependency.

[Unreleased]: https://github.com/vibhorxpandey/Aurelius-IDE/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/vibhorxpandey/Aurelius-IDE/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/vibhorxpandey/Aurelius-IDE/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/vibhorxpandey/Aurelius-IDE/releases/tag/v0.3.0
