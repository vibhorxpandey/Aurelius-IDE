import type { LspDiagnostic } from "@shared/lsp-types";
import { fileUriToPath } from "../lsp/client";
import { basename } from "../state/types";
import { ChevronIcon, ErrorIcon, WarningIcon, InfoIcon, HintIcon } from "./icons";
import TerminalPanel from "./Terminal";

interface ProblemEntry {
  uri: string;
  diagnostic: LspDiagnostic;
}

interface ProblemsPanelProps {
  diagnosticsByUri: Map<string, LspDiagnostic[]>;
  collapsed: boolean;
  onToggle: () => void;
  onJump: (uri: string, line: number) => void;
  bottomTab: "problems" | "terminal";
  onBottomTabChange: (tab: "problems" | "terminal") => void;
}

const ICON = { 1: ErrorIcon, 2: WarningIcon, 3: InfoIcon, 4: HintIcon } as const;

/**
 * Owns the whole bottom panel, not just Problems — Problems and the integrated Terminal
 * share one collapsible strip, VS Code-style. The terminal stays mounted (hidden via CSS,
 * not unmounted) whichever tab is active, because unmounting it would kill the real shell
 * process underneath every time you switched away and back.
 */
export default function ProblemsPanel({
  diagnosticsByUri,
  collapsed,
  onToggle,
  onJump,
  bottomTab,
  onBottomTabChange,
}: ProblemsPanelProps) {
  const entries: ProblemEntry[] = [];
  for (const [uri, diags] of diagnosticsByUri) {
    for (const diagnostic of diags) entries.push({ uri, diagnostic });
  }
  entries.sort((a, b) => a.diagnostic.severity - b.diagnostic.severity);

  const errors = entries.filter((e) => e.diagnostic.severity === 1).length;
  const warnings = entries.filter((e) => e.diagnostic.severity === 2).length;

  return (
    <div className="problems" data-collapsed={collapsed}>
      <div className="problems__header">
        <span
          style={{ transform: collapsed ? "rotate(-90deg)" : undefined, cursor: "pointer" }}
          onClick={onToggle}
        >
          <ChevronIcon size={12} />
        </span>
        <div className="problems__tabs">
          <span
            className="problems__tab"
            data-active={bottomTab === "problems"}
            onClick={() => onBottomTabChange("problems")}
          >
            Problems
          </span>
          <span
            className="problems__tab"
            data-active={bottomTab === "terminal"}
            onClick={() => onBottomTabChange("terminal")}
          >
            Terminal
          </span>
        </div>
        {bottomTab === "problems" && (
          <span className="problems__counts">
            <span>
              <ErrorIcon size={12} /> {errors}
            </span>
            <span>
              <WarningIcon size={12} /> {warnings}
            </span>
          </span>
        )}
      </div>

      <div
        className="problems__body"
        style={{ display: !collapsed && bottomTab === "problems" ? "block" : "none" }}
      >
        {entries.length === 0 ? (
          <div className="problems__empty">No problems in the workspace.</div>
        ) : (
          entries.map((entry, i) => {
            const Icon = ICON[entry.diagnostic.severity] ?? WarningIcon;
            return (
              <div
                key={`${entry.uri}:${i}`}
                className="problem-row"
                onClick={() => onJump(entry.uri, entry.diagnostic.range.start.line)}
              >
                <span className="problem-row__icon">
                  <Icon size={13} />
                </span>
                <div>
                  <span className="problem-row__message">{entry.diagnostic.message}</span>
                  <span className="problem-row__source">
                    {entry.diagnostic.source} {entry.diagnostic.code}
                  </span>
                  <div className="problem-row__file">
                    {basename(fileUriToPath(entry.uri))}:{entry.diagnostic.range.start.line + 1}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
      {/* Always mounted — collapsing the panel must not kill the shell process underneath. */}
      <TerminalPanel visible={!collapsed && bottomTab === "terminal"} />
    </div>
  );
}
