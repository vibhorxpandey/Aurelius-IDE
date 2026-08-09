import type { LspDiagnostic } from "@shared/lsp-types";
import { fileUriToPath } from "../lsp/client";
import { basename } from "../state/types";
import { ChevronIcon, ErrorIcon, WarningIcon, InfoIcon, HintIcon } from "./icons";

interface ProblemEntry {
  uri: string;
  diagnostic: LspDiagnostic;
}

interface ProblemsPanelProps {
  diagnosticsByUri: Map<string, LspDiagnostic[]>;
  collapsed: boolean;
  onToggle: () => void;
  onJump: (uri: string, line: number) => void;
}

const ICON = { 1: ErrorIcon, 2: WarningIcon, 3: InfoIcon, 4: HintIcon } as const;

export default function ProblemsPanel({
  diagnosticsByUri,
  collapsed,
  onToggle,
  onJump,
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
      <div className="problems__header" onClick={onToggle}>
        <span style={{ transform: collapsed ? "rotate(-90deg)" : undefined }}>
          <ChevronIcon size={12} />
        </span>
        <span className="problems__title">Problems</span>
        <span className="problems__counts">
          <span>
            <ErrorIcon size={12} /> {errors}
          </span>
          <span>
            <WarningIcon size={12} /> {warnings}
          </span>
        </span>
      </div>
      {!collapsed && (
        <div className="problems__body">
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
      )}
    </div>
  );
}
