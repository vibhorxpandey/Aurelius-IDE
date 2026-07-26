import * as vscode from "vscode";
import { AureliusClient, SearchResult } from "./client";

/**
 * Find a paper and cite it correctly without leaving the document.
 *
 * This closes the loop the rest of the extension only half-closes: the linter tells you a
 * citation is wrong, and this is how you get a right one. The inserted entry comes from
 * the index rather than from memory, so the key, the author list and the year are correct
 * by construction — which removes the most common way a bad citation enters a paper in
 * the first place.
 */
interface Pick extends vscode.QuickPickItem {
  result?: SearchResult;
}

function toPick(result: SearchResult): Pick {
  const authors =
    result.authors.length > 2
      ? `${result.authors[0]} et al.`
      : result.authors.join(" and ") || "unknown author";

  const meta = [authors, result.venue, result.year].filter(Boolean).join(" · ");
  const cites = result.cited_by ? `${result.cited_by.toLocaleString()} citations` : "";

  return {
    // A retracted hit is still shown — hiding it would mean the author finds it elsewhere
    // and cites it anyway. Better to surface it, labelled.
    label: result.is_retracted ? `$(error) ${result.title}` : result.title,
    description: cites,
    detail: result.is_retracted ? `RETRACTED · ${meta}` : meta,
    result,
  };
}

export async function findAndCite(client: AureliusClient): Promise<void> {
  if (!client.running) {
    void vscode.window.showWarningMessage("Aurelius: the language server is not running.");
    return;
  }

  const quickPick = vscode.window.createQuickPick<Pick>();
  quickPick.title = "Aurelius: find a paper";
  quickPick.placeholder = "Search OpenAlex by title, author, or topic";
  quickPick.matchOnDetail = true;

  // The index is queried as you type, so results must not be filtered again locally —
  // VS Code would otherwise hide hits whose relevance the index already judged.
  let generation = 0;
  const runSearch = async (value: string) => {
    const mine = ++generation;
    if (!value.trim()) {
      quickPick.items = [];
      return;
    }
    quickPick.busy = true;
    const response = await client.search(value, 12);
    // A slower earlier query must not overwrite a newer one's results.
    if (mine !== generation) {
      return;
    }
    quickPick.busy = false;

    if (!response) {
      quickPick.items = [{ label: "Search failed", detail: "See the Aurelius output channel" }];
      return;
    }
    if (!response.ok) {
      // "Unreachable" and "no such paper" are different answers and must read differently.
      quickPick.items = [
        { label: "$(cloud-offline) Literature index unreachable", detail: response.reason },
      ];
      return;
    }
    quickPick.items = response.results.length
      ? response.results.map(toPick)
      : [{ label: "No matches", detail: "Try fewer or more distinctive words" }];
  };

  let timer: NodeJS.Timeout | undefined;
  quickPick.onDidChangeValue((value) => {
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => void runSearch(value), 300);
  });

  const chosen = await new Promise<SearchResult | undefined>((resolve) => {
    quickPick.onDidAccept(() => resolve(quickPick.selectedItems[0]?.result));
    quickPick.onDidHide(() => resolve(undefined));
    quickPick.show();
  });
  if (timer) {
    clearTimeout(timer);
  }
  quickPick.dispose();

  if (!chosen) {
    return;
  }
  if (chosen.is_retracted) {
    const proceed = await vscode.window.showWarningMessage(
      `"${chosen.title}" has been retracted. Cite it anyway?`,
      { modal: true },
      "Cite anyway"
    );
    if (proceed !== "Cite anyway") {
      return;
    }
  }
  await insertCitation(chosen);
}

async function insertCitation(result: SearchResult): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return;
  }

  const bibUri = await resolveBibliography(editor.document.uri);
  if (!bibUri) {
    // No .bib to write to — put the entry on the clipboard rather than silently dropping
    // it, so the work of finding the paper is not lost.
    await vscode.env.clipboard.writeText(result.bibtex);
    void vscode.window.showWarningMessage(
      "No .bib file found beside this paper. The BibTeX entry was copied to your clipboard."
    );
    return;
  }

  const bibDoc = await vscode.workspace.openTextDocument(bibUri);
  if (bibDoc.getText().includes(`{${result.key},`)) {
    // Already present. Insert the \cite and leave the bibliography alone.
    await editor.edit((edit) => edit.replace(editor.selection, `\\cite{${result.key}}`));
    void vscode.window.showInformationMessage(`'${result.key}' is already in your bibliography.`);
    return;
  }

  const edit = new vscode.WorkspaceEdit();
  edit.replace(editor.document.uri, editor.selection, `\\cite{${result.key}}`);
  edit.insert(
    bibUri,
    new vscode.Position(bibDoc.lineCount, 0),
    `\n${result.bibtex}\n`
  );
  await vscode.workspace.applyEdit(edit);
  void vscode.window.showInformationMessage(
    `Cited '${result.key}' and added it to ${vscode.workspace.asRelativePath(bibUri)}.`
  );
}

/** The `.bib` this paper writes to: the one it declares, else any sibling. */
async function resolveBibliography(texUri: vscode.Uri): Promise<vscode.Uri | undefined> {
  const doc = await vscode.workspace.openTextDocument(texUri);
  const declared = /\\(?:bibliography|addbibresource)\s*\{([^}]*)\}/.exec(doc.getText());
  const dir = vscode.Uri.joinPath(texUri, "..");

  if (declared) {
    for (const raw of declared[1].split(",")) {
      const name = raw.trim();
      if (!name) {
        continue;
      }
      const candidate = vscode.Uri.joinPath(dir, name.endsWith(".bib") ? name : `${name}.bib`);
      try {
        await vscode.workspace.fs.stat(candidate);
        return candidate;
      } catch {
        // Declared but absent — fall through to the sibling scan.
      }
    }
  }

  const siblings = await vscode.workspace.findFiles(
    new vscode.RelativePattern(dir, "*.bib"),
    undefined,
    1
  );
  return siblings[0];
}
