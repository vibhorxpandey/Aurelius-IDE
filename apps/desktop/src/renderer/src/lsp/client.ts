/**
 * A minimal LSP client over the IPC transport `main/lspServer.ts` provides.
 *
 * Not `monaco-languageclient` — that expects a WebSocket, which would mean running a
 * local server purely to talk to a process this app already owns. This is the ~120 lines
 * that are actually needed: request/response correlation by id, notifications, and a
 * diagnostics subscription. It talks to the *real* `aurelius-lsp`; nothing here is mocked.
 */
import type {
  JsonRpcMessage,
  LspDiagnostic,
  PublishDiagnosticsParams,
  ServerStatus,
} from "@shared/lsp-types";
import { getApi } from "../platform";

/**
 * One real step of the OpenAlex -> Crossref -> arXiv -> Semantic Scholar cascade,
 * pushed the moment `aurelius_ide.engine` fires it — see `lsp.py::_publish_progress`.
 * `status` is "checking" while the request is in flight, then "hit" or "miss".
 */
export interface VerificationProgressEvent {
  uri: string;
  key: string;
  source: string;
  status: "checking" | "hit" | "miss";
}

type DiagnosticsListener = (uri: string, diagnostics: LspDiagnostic[]) => void;
type StatusListener = (status: ServerStatus) => void;
type ProgressListener = (step: VerificationProgressEvent) => void;

export class LspClient {
  private nextId = 1;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private diagnosticsListeners = new Set<DiagnosticsListener>();
  private statusListeners = new Set<StatusListener>();
  private progressListeners = new Set<ProgressListener>();
  private latestDiagnostics = new Map<string, LspDiagnostic[]>();
  private initialized: Promise<void> | null = null;
  private unsubscribeMessage: () => void;
  private unsubscribeStatus: () => void;
  private lastStatus: ServerStatus = { state: "starting", detail: "" };

  private readonly api = getApi();

  constructor(private readonly rootPath: string) {
    const api = this.api;
    this.unsubscribeMessage = api.lsp.onMessage((message) => this.handleMessage(message));
    this.unsubscribeStatus = api.lsp.onStatus((status) => {
      this.lastStatus = status;
      this.statusListeners.forEach((l) => l(status));
      if (status.state === "running") void this.ensureInitialized();
    });
  }

  get status(): ServerStatus {
    return this.lastStatus;
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.lastStatus);
    return () => this.statusListeners.delete(listener);
  }

  onDiagnostics(listener: DiagnosticsListener): () => void {
    this.diagnosticsListeners.add(listener);
    for (const [uri, diags] of this.latestDiagnostics) listener(uri, diags);
    return () => this.diagnosticsListeners.delete(listener);
  }

  /** Fire-and-forget: a client that never calls this loses nothing, same as the server
   * side treats it — see the docstring on `_publish_progress` in `lsp.py`. */
  onProgress(listener: ProgressListener): () => void {
    this.progressListeners.add(listener);
    return () => this.progressListeners.delete(listener);
  }

  diagnosticsFor(uri: string): LspDiagnostic[] {
    return this.latestDiagnostics.get(uri) ?? [];
  }

  /** Total findings across every file the server has analysed — the status-bar summary. */
  get allDiagnostics(): Map<string, LspDiagnostic[]> {
    return this.latestDiagnostics;
  }

  private ensureInitialized(): Promise<void> {
    if (!this.initialized) {
      this.initialized = this.doInitialize();
    }
    return this.initialized;
  }

  private async doInitialize(): Promise<void> {
    // Real LSP handshake — the server (pygls) will not process most requests before this
    // completes, so skipping it is not a shortcut, it is a bug that shows up as silence.
    await this.request("initialize", {
      processId: null,
      rootUri: pathToFileUri(this.rootPath),
      capabilities: {
        textDocument: {
          publishDiagnostics: { relatedInformation: false },
          hover: { contentFormat: ["markdown", "plaintext"] },
          codeAction: { codeActionLiteralSupport: { codeActionKind: { valueSet: ["quickfix"] } } },
        },
        workspace: { executeCommand: {}, workspaceFolders: false },
      },
      workspaceFolders: null,
    });
    this.notify("initialized", {});
  }

  async didOpen(uri: string, languageId: string, version: number, text: string): Promise<void> {
    await this.ensureInitialized();
    this.notify("textDocument/didOpen", {
      textDocument: { uri, languageId, version, text },
    });
  }

  didChange(uri: string, version: number, text: string): void {
    // Full-document sync: one entry with no range, which is always a valid change event
    // regardless of what incremental-sync capability the server negotiated.
    this.notify("textDocument/didChange", {
      textDocument: { uri, version },
      contentChanges: [{ text }],
    });
  }

  didSave(uri: string): void {
    this.notify("textDocument/didSave", { textDocument: { uri } });
  }

  didClose(uri: string): void {
    this.notify("textDocument/didClose", { textDocument: { uri } });
  }

  async hover(uri: string, line: number, character: number): Promise<{ value: string } | null> {
    const result = (await this.request("textDocument/hover", {
      textDocument: { uri },
      position: { line, character },
    })) as { contents?: { value?: string } | string } | null;
    if (!result?.contents) return null;
    const value = typeof result.contents === "string" ? result.contents : result.contents.value;
    return value ? { value } : null;
  }

  async codeActions(
    uri: string,
    range: { start: { line: number; character: number }; end: { line: number; character: number } }
  ): Promise<unknown[]> {
    const diagnostics = this.diagnosticsFor(uri).filter(
      (d) => d.range.start.line <= range.start.line && d.range.end.line >= range.start.line
    );
    const result = await this.request("textDocument/codeAction", {
      textDocument: { uri },
      range,
      context: { diagnostics },
    });
    return Array.isArray(result) ? result : [];
  }

  async executeCommand<T>(command: string, args: unknown[]): Promise<T> {
    return (await this.request("workspace/executeCommand", { command, arguments: args })) as T;
  }

  private request(method: string, params: unknown): Promise<unknown> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.api.lsp.send({ jsonrpc: "2.0", id, method, params });
    });
  }

  private notify(method: string, params: unknown): void {
    this.api.lsp.send({ jsonrpc: "2.0", method, params });
  }

  private handleMessage(message: JsonRpcMessage): void {
    if (message.id !== undefined && (message.result !== undefined || message.error)) {
      const waiter = this.pending.get(message.id as number);
      if (waiter) {
        this.pending.delete(message.id as number);
        if (message.error) waiter.reject(new Error(message.error.message));
        else waiter.resolve(message.result);
      }
      return;
    }
    if (message.method === "textDocument/publishDiagnostics") {
      const params = message.params as PublishDiagnosticsParams;
      this.latestDiagnostics.set(params.uri, params.diagnostics);
      this.diagnosticsListeners.forEach((l) => l(params.uri, params.diagnostics));
      return;
    }
    if (message.method === "aurelius/verificationProgress") {
      const step = message.params as VerificationProgressEvent;
      this.progressListeners.forEach((l) => l(step));
    }
  }

  dispose(): void {
    this.unsubscribeMessage();
    this.unsubscribeStatus();
  }
}

export function pathToFileUri(path: string): string {
  const normalised = path.replace(/\\/g, "/");
  const withSlash = normalised.startsWith("/") ? normalised : `/${normalised}`;
  return `file://${encodeURI(withSlash).replace(/#/g, "%23")}`;
}

export function fileUriToPath(uri: string): string {
  const decoded = decodeURIComponent(uri.replace(/^file:\/\//, ""));
  // A Windows path like /C:/Users/... needs the leading slash stripped; a POSIX path does
  // not, so the check is on the drive-letter pattern rather than the platform.
  return /^\/[A-Za-z]:/.test(decoded) ? decoded.slice(1) : decoded;
}
