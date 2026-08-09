/**
 * The slice of LSP + Aurelius's own command shapes that the renderer needs.
 *
 * Kept separate from `main`/`renderer` so both sides typecheck against the same contract —
 * the exact problem `check_command_contract.py` exists to catch on the VS Code extension
 * side, done here with the type checker instead of a script, since main and renderer are
 * already compiled together.
 */

export interface JsonRpcMessage {
  jsonrpc: "2.0";
  id?: number | string;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

export interface LspPosition {
  line: number;
  character: number;
}

export interface LspRange {
  start: LspPosition;
  end: LspPosition;
}

/** Mirrors `Diagnostic.to_lsp()` in `diagnostics.py`. */
export interface LspDiagnostic {
  range: LspRange;
  message: string;
  severity: 1 | 2 | 3 | 4;
  code: string;
  source: string;
  data: Record<string, unknown>;
}

export interface PublishDiagnosticsParams {
  uri: string;
  version?: number;
  diagnostics: LspDiagnostic[];
}

/** Mirrors `bibliography_status()` in `lsp.py`. */
export interface BibEntryStatus {
  key: string;
  title: string;
  author: string;
  year: string;
  doi: string;
  venue: string;
  entryType: string;
  citedOnLines: number[];
  citeCount: number;
  verdict: "verified" | "unverified" | "not_found" | "retracted" | "unchecked";
  confidence: string;
  notes: string;
  bibLine: number;
}

export interface BibliographyStatus {
  ok: boolean;
  reason?: string;
  entries: BibEntryStatus[];
  bibUri: string;
  counts: Record<string, number>;
}

/** Mirrors `submission_gate()` in `lsp.py`. */
export interface GateCheck {
  label: string;
  status: "pass" | "fail" | "skip";
  count: number;
  blocking: boolean;
  detail: string;
}

export interface GateResult {
  ok: boolean;
  reason?: string;
  checks: GateCheck[];
  blocking: number;
  skipped: number;
  ready: boolean;
  references: number;
}

export interface SearchResult {
  key: string;
  title: string;
  authors: string[];
  year: string;
  doi: string;
  venue: string;
  cited_by: number;
  is_retracted: boolean;
  bibtex: string;
}

export interface FsEntry {
  name: string;
  path: string;
  isDirectory: boolean;
}

export interface ServerStatus {
  state: "starting" | "running" | "crashed" | "not-found";
  detail: string;
  version?: string;
}

/**
 * The contextBridge surface, defined once here so main, preload and renderer all
 * typecheck against the same contract without any of them reaching into another
 * project's source tree — `preload/index.ts` implements this shape, `preload/index.d.ts`
 * re-exports it onto `Window`, and the renderer imports it directly from here.
 */
export interface AureliusApi {
  workspace: {
    defaultPath: () => Promise<string>;
    list: (path: string) => Promise<FsEntry[]>;
    read: (path: string) => Promise<string>;
    write: (path: string, content: string) => Promise<void>;
    isDirectory: (path: string) => Promise<boolean>;
    openFolderDialog: () => Promise<string | null>;
  };
  lsp: {
    send: (message: JsonRpcMessage) => void;
    restart: () => Promise<void>;
    onMessage: (handler: (message: JsonRpcMessage) => void) => () => void;
    onStatus: (handler: (status: ServerStatus) => void) => () => void;
    onStderr: (handler: (text: string) => void) => () => void;
  };
}
