import type { LspClient } from "../lsp/client";
import { PlayIcon, CheckCircleIcon, ErrorIcon } from "./icons";

export interface CompilePdfResult {
  ok: boolean;
  reason?: string;
  pdfPath?: string | null;
  pdfUri?: string | null;
  log?: string;
  diagnostics?: number;
  errors?: number;
}

interface RunAndDebugPanelProps {
  client: LspClient | null;
  activeUri: string | null;
  running: boolean;
  lastResult: CompilePdfResult | null;
  onRun: () => void;
  onShowPdf: () => void;
}

/**
 * "Run" for a paper means one thing: compile it to a PDF. There is no meaningful notion
 * of breakpoints or a call stack for a LaTeX document, so this deliberately doesn't
 * pretend to be a general-purpose debugger — it is the real compile-and-show-me-the-PDF
 * action, framed in the position VS Code puts Run and Debug, with real output landing in
 * the Debug Console below rather than a placeholder.
 */
export default function RunAndDebugPanel({
  client,
  activeUri,
  running,
  lastResult,
  onRun,
  onShowPdf,
}: RunAndDebugPanelProps) {
  if (!client) {
    return <div className="sidebar__empty">Language server unavailable.</div>;
  }
  if (!activeUri) {
    return <div className="sidebar__empty">Open a .tex file to compile it.</div>;
  }

  return (
    <div>
      <div className="sidebar-section">
        <span>Run and debug</span>
      </div>

      <div
        className="gate-run-btn"
        onClick={running ? undefined : onRun}
        aria-disabled={running}
        style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
      >
        <PlayIcon size={12} />
        <span>{running ? "Compiling…" : "Compile paper.tex → PDF"}</span>
      </div>

      {lastResult && (
        <div className="panel-list">
          {!lastResult.ok ? (
            <div className="gate-check">
              <span style={{ marginTop: 2 }}>
                <ErrorIcon size={14} />
              </span>
              <div>
                <div className="gate-check__label">Could not compile</div>
                <div className="gate-check__meta">{lastResult.reason}</div>
              </div>
            </div>
          ) : (
            <>
              <div className="gate-check">
                <span style={{ marginTop: 2 }}>
                  {lastResult.errors ? <ErrorIcon size={14} /> : <CheckCircleIcon size={14} />}
                </span>
                <div>
                  <div className="gate-check__label">
                    {lastResult.pdfPath ? "PDF produced" : "No PDF produced"}
                  </div>
                  <div className="gate-check__meta">
                    {lastResult.diagnostics ?? 0} finding{(lastResult.diagnostics ?? 0) === 1 ? "" : "s"}
                    {lastResult.errors ? ` · ${lastResult.errors} error${lastResult.errors === 1 ? "" : "s"}` : ""}
                  </div>
                </div>
              </div>
              {lastResult.pdfPath && (
                <div className="gate-run-btn" style={{ background: "transparent", border: "1px solid var(--border-strong)", color: "var(--fg-default)" }} onClick={onShowPdf}>
                  View compiled PDF
                </div>
              )}
            </>
          )}
        </div>
      )}

      <p className="login__note" style={{ margin: "16px 16px 0" }}>
        Real output — the exact transcript from the toolchain — lands in the Debug Console
        tab below.
      </p>
    </div>
  );
}
