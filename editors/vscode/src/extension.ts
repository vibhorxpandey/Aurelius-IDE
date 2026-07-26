import * as vscode from "vscode";
import { AureliusClient, activeTexUri } from "./client";
import { BibliographyProvider } from "./bibliographyView";
import { GateProvider } from "./gateView";
import { findAndCite } from "./literatureSearch";

let client: AureliusClient | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  client = new AureliusClient(context);
  await client.start();

  const bibliography = new BibliographyProvider(client);
  const gate = new GateProvider(client);

  const bibView = vscode.window.createTreeView("aurelius.bibliography", {
    treeDataProvider: bibliography,
    showCollapseAll: false,
  });
  const gateView = vscode.window.createTreeView("aurelius.gate", { treeDataProvider: gate });
  context.subscriptions.push(bibView, gateView);

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  status.command = "aurelius.showBibliography";
  context.subscriptions.push(status);

  const refresh = async () => {
    bibliography.refresh();
    // The tree title carries the count, so it is legible without expanding the view.
    const summary = await pollDescription(bibliography);
    bibView.description = summary;
    updateStatus(status, summary);
  };

  context.subscriptions.push(
    client.onDidChange(() => void refresh()),
    vscode.window.onDidChangeActiveTextEditor(() => void refresh()),
    // Re-verification is debounced server-side; this only re-reads what it published.
    vscode.workspace.onDidSaveTextDocument(() => void refresh()),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.uri.toString() === activeTexUri()) {
        void refresh();
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("aurelius.restart", async () => {
      await client?.restart();
      gate.reset();
      void vscode.window.showInformationMessage("Aurelius restarted.");
    }),

    vscode.commands.registerCommand("aurelius.refreshBibliography", () => void refresh()),

    vscode.commands.registerCommand("aurelius.showBibliography", () =>
      vscode.commands.executeCommand("aurelius.bibliography.focus")
    ),

    vscode.commands.registerCommand("aurelius.findAndCite", async () => {
      if (client) {
        await findAndCite(client);
        void refresh();
      }
    }),

    vscode.commands.registerCommand("aurelius.runSubmissionGate", async () => {
      await gate.run();
      await vscode.commands.executeCommand("aurelius.gate.focus");
    }),

    vscode.commands.registerCommand("aurelius.compileGate", async () => {
      const uri = activeTexUri();
      if (!uri || !client) {
        void vscode.window.showWarningMessage("Open a .tex file to run the compile gate.");
        return;
      }
      const result = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Window, title: "Aurelius: compiling…" },
        () => client!.compileGate(uri)
      );
      if (result && !result.ok) {
        // "No toolchain" is not "your paper is broken" — say which one it was.
        void vscode.window.showWarningMessage(`Aurelius: ${result.reason}`);
      }
      void refresh();
    }),

    vscode.commands.registerCommand("aurelius.verifyAll", async () => {
      const uri = activeTexUri();
      if (uri) {
        await vscode.commands.executeCommand("workbench.action.files.save");
        void refresh();
      }
    }),

    vscode.commands.registerCommand(
      "aurelius.revealEntry",
      async (bibUri: string, line: number) => {
        if (!bibUri) {
          return;
        }
        const doc = await vscode.workspace.openTextDocument(vscode.Uri.parse(bibUri));
        const editor = await vscode.window.showTextDocument(doc, { preview: true });
        const position = new vscode.Position(Math.max(0, line), 0);
        editor.selection = new vscode.Selection(position, position);
        editor.revealRange(
          new vscode.Range(position, position),
          vscode.TextEditorRevealType.InCenter
        );
      }
    )
  );

  void refresh();
}

/** Read the provider's summary after its children have been produced. */
async function pollDescription(provider: BibliographyProvider): Promise<string> {
  await provider.getChildren();
  return provider.description;
}

function updateStatus(item: vscode.StatusBarItem, summary: string): void {
  if (!summary || !activeTexUri()) {
    item.hide();
    return;
  }
  const problems = /(\d+) problem/.exec(summary);
  item.text = problems ? `$(book) ${summary}` : `$(book) ${summary}`;
  item.backgroundColor = problems
    ? new vscode.ThemeColor("statusBarItem.warningBackground")
    : undefined;
  item.tooltip = "Aurelius: show bibliography";
  item.show();
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
