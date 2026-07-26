import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

/**
 * Resolve how to launch the server.
 *
 * Two supported shapes: the `aurelius-lsp` console script on PATH (the normal case
 * after `pip install aurelius-ide[all]`), or an explicit interpreter running the module,
 * which is what you want inside a virtualenv or a conda environment.
 */
function buildServerOptions(): ServerOptions {
  const config = vscode.workspace.getConfiguration("aurelius");
  const pythonPath = config.get<string>("pythonPath", "").trim();

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

function buildClientOptions(): LanguageClientOptions {
  return {
    documentSelector: [
      { scheme: "file", language: "latex" },
      { scheme: "file", language: "tex" },
      { scheme: "file", language: "bibtex" },
    ],
    synchronize: {
      // A .bib edit changes diagnostics in every .tex that cites it, so the server
      // needs to see those changes even when the .bib isn't the active editor.
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.{tex,bib}"),
      configurationSection: "aurelius",
    },
    outputChannel: vscode.window.createOutputChannel("Aurelius"),
  };
}

async function start(context: vscode.ExtensionContext): Promise<void> {
  client = new LanguageClient(
    "aurelius",
    "Aurelius Research Linter",
    buildServerOptions(),
    buildClientOptions()
  );

  try {
    await client.start();
    context.subscriptions.push(client);
  } catch (error) {
    // The overwhelmingly common failure is that the Python package isn't installed.
    // Say that plainly instead of surfacing a raw spawn ENOENT.
    void vscode.window.showErrorMessage(
      `Aurelius could not start its language server. Install it with ` +
        `\`pip install "aurelius-ide[all]"\`, or set aurelius.pythonPath to the ` +
        `interpreter where it lives. (${error})`
    );
  }
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  await start(context);

  context.subscriptions.push(
    vscode.commands.registerCommand("aurelius.restart", async () => {
      await client?.stop();
      client = undefined;
      await start(context);
      void vscode.window.showInformationMessage("Aurelius restarted.");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("aurelius.verifyAll", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        return;
      }
      // Re-open forces a full pass rather than an incremental one, which is what
      // "verify everything now" should mean.
      await client?.sendNotification("textDocument/didSave", {
        textDocument: { uri: editor.document.uri.toString() },
      });
      void vscode.window.showInformationMessage("Aurelius: verifying bibliography…");
    })
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
