import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

/** Server-side command ids. Must match the constants in `aurelius_ide/lsp.py`. */
export const COMMANDS = {
  compileGate: "aurelius.compileGate",
  bibliography: "aurelius.bibliographyStatus",
  search: "aurelius.searchLiterature",
  submissionGate: "aurelius.submissionGate",
} as const;

export type Verdict =
  | "verified"
  | "unverified"
  | "not_found"
  | "retracted"
  | "unchecked";

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
  verdict: Verdict;
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

/**
 * Owns the language client and is the single place that talks to the server.
 *
 * Views depend on this rather than on a `LanguageClient` directly, so a restart swaps the
 * client underneath them without every view needing to re-subscribe.
 */
export class AureliusClient {
  private client: LanguageClient | undefined;
  private readonly output: vscode.OutputChannel;
  private readonly changed = new vscode.EventEmitter<void>();

  /** Fires whenever server state may have moved — views refresh off this. */
  readonly onDidChange = this.changed.event;

  constructor(private readonly context: vscode.ExtensionContext) {
    this.output = vscode.window.createOutputChannel("Aurelius");
    context.subscriptions.push(this.output, this.changed);
  }

  get running(): boolean {
    return this.client !== undefined;
  }

  private serverOptions(): ServerOptions {
    const config = vscode.workspace.getConfiguration("aurelius");
    const pythonPath = config.get<string>("pythonPath", "").trim();

    // Two supported shapes: the console script on PATH (normal after pip install), or an
    // explicit interpreter running the module — what you need inside a venv or conda env.
    if (pythonPath) {
      return {
        command: pythonPath,
        args: ["-m", "aurelius_ide.lsp"],
        transport: TransportKind.stdio,
      };
    }
    return {
      command: config.get<string>("serverPath", "aurelius-lsp"),
      args: [],
      transport: TransportKind.stdio,
    };
  }

  private clientOptions(): LanguageClientOptions {
    return {
      documentSelector: [
        { scheme: "file", language: "latex" },
        { scheme: "file", language: "tex" },
        { scheme: "file", language: "bibtex" },
      ],
      synchronize: {
        // A .bib edit changes diagnostics in every .tex that cites it, so the server needs
        // those changes even when the .bib is not the active editor.
        fileEvents: vscode.workspace.createFileSystemWatcher("**/*.{tex,bib}"),
      },
      outputChannel: this.output,
    };
  }

  async start(): Promise<boolean> {
    this.client = new LanguageClient(
      "aurelius",
      "Aurelius Research Linter",
      this.serverOptions(),
      this.clientOptions()
    );
    try {
      await this.client.start();
      this.context.subscriptions.push(this.client);
      this.changed.fire();
      return true;
    } catch (error) {
      this.client = undefined;
      // The overwhelmingly common failure is that the Python package is not installed.
      // Say that, and offer the fix, rather than surfacing a raw spawn ENOENT.
      const install = "Show install command";
      const choice = await vscode.window.showErrorMessage(
        "Aurelius could not start its language server. The Python package may not be installed.",
        install,
        "Open output"
      );
      if (choice === install) {
        void vscode.window.showInformationMessage(
          'pip install "aurelius-ide[all] @ git+https://github.com/vibhorxpandey/Aurelius-IDE"',
          { modal: false }
        );
      } else if (choice === "Open output") {
        this.output.show();
      }
      this.output.appendLine(`Failed to start language server: ${error}`);
      return false;
    }
  }

  async stop(): Promise<void> {
    const client = this.client;
    this.client = undefined;
    await client?.stop();
    this.changed.fire();
  }

  async restart(): Promise<void> {
    await this.stop();
    await this.start();
  }

  /** Nudge views to refresh. Called after edits and after a gate run. */
  notifyChanged(): void {
    this.changed.fire();
  }

  private async execute<T>(command: string, args: unknown[]): Promise<T | undefined> {
    if (!this.client) {
      return undefined;
    }
    try {
      return (await this.client.sendRequest("workspace/executeCommand", {
        command,
        arguments: args,
      })) as T;
    } catch (error) {
      this.output.appendLine(`${command} failed: ${error}`);
      return undefined;
    }
  }

  bibliography(uri: string): Promise<BibliographyStatus | undefined> {
    return this.execute<BibliographyStatus>(COMMANDS.bibliography, [uri]);
  }

  search(query: string, limit = 10): Promise<{ ok: boolean; reason?: string; results: SearchResult[] } | undefined> {
    return this.execute(COMMANDS.search, [query, limit]);
  }

  submissionGate(uri: string): Promise<GateResult | undefined> {
    return this.execute<GateResult>(COMMANDS.submissionGate, [uri]);
  }

  compileGate(uri: string): Promise<{ ok: boolean; reason?: string } | undefined> {
    return this.execute(COMMANDS.compileGate, [uri]);
  }
}

/** The active `.tex` document, if the editor is on one. */
export function activeTexUri(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return undefined;
  }
  const id = editor.document.languageId;
  if (id !== "latex" && id !== "tex") {
    return undefined;
  }
  return editor.document.uri.toString();
}
