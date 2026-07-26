import * as vscode from "vscode";
import { AureliusClient, BibEntryStatus, Verdict, activeTexUri } from "./client";

/**
 * The bibliography as a list of works with live verdicts.
 *
 * Squiggles tell you about the citation site you happen to be looking at. This answers
 * the question an author actually has before submitting — *is anything in my bibliography
 * wrong?* — without making them scroll the whole paper to find out.
 *
 * Sort order is by severity, not alphabetically: a retracted reference is the reason to
 * open this panel, so it is never below the fold.
 */
const SEVERITY_RANK: Record<Verdict, number> = {
  retracted: 0,
  not_found: 1,
  unverified: 2,
  unchecked: 3,
  verified: 4,
};

const PRESENTATION: Record<
  Verdict,
  { icon: string; colour: string | undefined; label: string }
> = {
  retracted: { icon: "error", colour: "errorForeground", label: "RETRACTED" },
  not_found: { icon: "close", colour: "errorForeground", label: "not in any index" },
  unverified: { icon: "warning", colour: "editorWarning.foreground", label: "unverified" },
  unchecked: { icon: "circle-outline", colour: "disabledForeground", label: "unchecked" },
  verified: { icon: "pass-filled", colour: "testing.iconPassed", label: "verified" },
};

export class BibliographyItem extends vscode.TreeItem {
  constructor(
    readonly entry: BibEntryStatus,
    readonly bibUri: string
  ) {
    super(entry.key, vscode.TreeItemCollapsibleState.None);

    const look = PRESENTATION[entry.verdict] ?? PRESENTATION.unchecked;
    this.iconPath = new vscode.ThemeIcon(
      look.icon,
      look.colour ? new vscode.ThemeColor(look.colour) : undefined
    );

    const bits = [look.label];
    if (entry.citeCount === 0) {
      bits.push("uncited");
    } else if (entry.citeCount > 1) {
      bits.push(`${entry.citeCount}×`);
    }
    this.description = bits.join(" · ");

    this.tooltip = new vscode.MarkdownString(
      [
        `**${entry.title || entry.key}**`,
        "",
        entry.author ? `*${entry.author}*` : "",
        [entry.year, entry.venue, `@${entry.entryType}`].filter(Boolean).join(" · "),
        entry.doi ? `[doi:${entry.doi}](https://doi.org/${entry.doi})` : "",
        "",
        `---`,
        `${look.label}${entry.confidence ? ` (${entry.confidence} confidence)` : ""}`,
        entry.notes || "",
      ]
        .filter(Boolean)
        .join("\n\n")
    );

    // Clicking reveals the entry in the .bib rather than the citation site: this panel is
    // about the bibliography, and the entry is what you would edit.
    if (bibUri) {
      this.command = {
        command: "aurelius.revealEntry",
        title: "Reveal entry",
        arguments: [bibUri, entry.bibLine],
      };
    }
    this.contextValue = `aurelius.entry.${entry.verdict}`;
  }
}

class MessageItem extends vscode.TreeItem {
  constructor(label: string, icon = "info") {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
  }
}

export class BibliographyProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  private summary = "";

  constructor(private readonly client: AureliusClient) {}

  refresh(): void {
    this.changed.fire();
  }

  /** Rendered into the view title, so the count is visible without expanding anything. */
  get description(): string {
    return this.summary;
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: vscode.TreeItem): Promise<vscode.TreeItem[]> {
    if (element) {
      return [];
    }
    if (!this.client.running) {
      this.summary = "";
      return [new MessageItem("Language server is not running", "debug-disconnect")];
    }

    const uri = activeTexUri();
    if (!uri) {
      this.summary = "";
      return [new MessageItem("Open a .tex file to see its bibliography", "file")];
    }

    const status = await this.client.bibliography(uri);
    if (!status || !status.ok) {
      this.summary = "";
      return [new MessageItem(status?.reason ?? "No analysis yet", "sync")];
    }
    if (status.entries.length === 0) {
      this.summary = "";
      return [new MessageItem("No bibliography entries found", "book")];
    }

    const counts = status.counts ?? {};
    const problems =
      (counts.retracted ?? 0) + (counts.not_found ?? 0) + (counts.unverified ?? 0);
    this.summary =
      problems > 0
        ? `${status.entries.length} refs · ${problems} problem${problems === 1 ? "" : "s"}`
        : `${status.entries.length} refs`;

    const sorted = [...status.entries].sort((a, b) => {
      const rank = (SEVERITY_RANK[a.verdict] ?? 9) - (SEVERITY_RANK[b.verdict] ?? 9);
      return rank !== 0 ? rank : a.key.localeCompare(b.key);
    });
    return sorted.map((entry) => new BibliographyItem(entry, status.bibUri));
  }
}
