import * as vscode from "vscode";
import { AureliusClient, GateCheck, activeTexUri } from "./client";

/**
 * The pre-submission checklist.
 *
 * Every check reports pass, fail, or **skip** — and a skipped check never counts as a
 * passed one. If no TeX toolchain is installed, "the paper compiles" is unknown, and the
 * gate withholds its verdict rather than granting it. That is the same rule the analyzer
 * follows for an unreachable index: the tool must never imply it checked something it
 * could not check, because that is exactly the claim someone would submit on.
 */
const LOOK: Record<GateCheck["status"], { icon: string; colour: string }> = {
  pass: { icon: "pass-filled", colour: "testing.iconPassed" },
  fail: { icon: "error", colour: "errorForeground" },
  skip: { icon: "circle-slash", colour: "disabledForeground" },
};

class CheckItem extends vscode.TreeItem {
  constructor(check: GateCheck) {
    super(check.label, vscode.TreeItemCollapsibleState.None);
    const look = LOOK[check.status];
    this.iconPath = new vscode.ThemeIcon(look.icon, new vscode.ThemeColor(look.colour));

    if (check.status === "skip") {
      this.description = "did not run";
    } else if (check.count > 0) {
      this.description = `${check.count} issue${check.count === 1 ? "" : "s"}`;
    }
    if (check.blocking && check.status !== "pass") {
      this.description = `${this.description ?? ""} · blocking`.trim();
    }
    this.tooltip = check.detail || undefined;
  }
}

class VerdictItem extends vscode.TreeItem {
  constructor(label: string, icon: string, colour: string, detail: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon, new vscode.ThemeColor(colour));
    this.description = detail;
  }
}

class HintItem extends vscode.TreeItem {
  constructor(label: string, icon = "info") {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
  }
}

export class GateProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  private items: vscode.TreeItem[] = [
    new HintItem("Run the submission gate to check this paper", "play"),
  ];
  private running = false;

  constructor(private readonly client: AureliusClient) {}

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.TreeItem[] {
    return element ? [] : this.items;
  }

  reset(): void {
    this.items = [new HintItem("Run the submission gate to check this paper", "play")];
    this.changed.fire();
  }

  /** Runs the gate. Compiles the paper, so it is slow and never automatic. */
  async run(): Promise<void> {
    if (this.running) {
      return;
    }
    const uri = activeTexUri();
    if (!uri) {
      void vscode.window.showWarningMessage("Open a .tex file to run the submission gate.");
      return;
    }

    this.running = true;
    this.items = [new HintItem("Compiling and checking…", "loading~spin")];
    this.changed.fire();

    try {
      const result = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "Aurelius: submission gate" },
        () => this.client.submissionGate(uri)
      );

      if (!result || !result.ok) {
        this.items = [new HintItem(result?.reason ?? "The gate could not run", "warning")];
        return;
      }

      const checks = result.checks.map((c) => new CheckItem(c));
      let verdict: VerdictItem;
      if (result.blocking > 0) {
        verdict = new VerdictItem(
          "NOT READY",
          "error",
          "errorForeground",
          `${result.blocking} blocking`
        );
      } else if (result.skipped > 0) {
        // Deliberately not "ready". Some blocking check did not run.
        verdict = new VerdictItem(
          "INCONCLUSIVE",
          "circle-slash",
          "editorWarning.foreground",
          `${result.skipped} check${result.skipped === 1 ? "" : "s"} did not run`
        );
      } else {
        verdict = new VerdictItem(
          "READY TO SUBMIT",
          "pass-filled",
          "testing.iconPassed",
          `${result.references} references`
        );
      }
      this.items = [verdict, ...checks];
    } finally {
      this.running = false;
      this.changed.fire();
      this.client.notifyChanged();
    }
  }
}
