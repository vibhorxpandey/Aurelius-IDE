import { useState } from "react";
import type { GateResult } from "@shared/lsp-types";
import type { LspClient } from "../lsp/client";
import { PlayIcon, CheckCircleIcon, ErrorIcon, SkipCircleIcon } from "./icons";

interface GatePanelProps {
  client: LspClient | null;
  activeUri: string | null;
  onActivity?: (title: string, details: string[]) => void;
}

export default function GatePanel({ client, activeUri, onActivity }: GatePanelProps) {
  const [result, setResult] = useState<GateResult | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    if (!client || !activeUri || running) return;
    setRunning(true);
    try {
      const r = await client.executeCommand<GateResult>("aurelius.submissionGate", [activeUri]);
      setResult(r);
      if (r.ok) {
        const status = r.blocking > 0 ? "NOT READY" : r.skipped > 0 ? "INCONCLUSIVE" : "READY";
        onActivity?.(
          `Submission gate: ${status}`,
          r.checks.map((c) => `[${c.status}] ${c.label}`)
        );
      } else {
        onActivity?.("Submission gate could not run", [r.reason ?? "unknown reason"]);
      }
    } finally {
      setRunning(false);
    }
  };

  if (!client) {
    return <div className="sidebar__empty">Language server unavailable.</div>;
  }
  if (!activeUri) {
    return <div className="sidebar__empty">Open a .tex file to run the submission gate.</div>;
  }

  const status = !result ? null : result.blocking > 0 ? "not-ready" : result.skipped > 0 ? "inconclusive" : "ready";

  return (
    <div>
      <div className="sidebar-section">
        <span>Submission gate</span>
      </div>
      <div
        className="gate-run-btn"
        onClick={() => void run()}
        aria-disabled={running}
        style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
      >
        <PlayIcon size={12} />
        <span>{running ? "Compiling and checking…" : "Run submission gate"}</span>
      </div>

      {result?.ok === false && <div className="sidebar__empty">{result.reason}</div>}

      {result?.ok && (
        <>
          <div className="gate-summary" data-status={status ?? undefined}>
            {status === "ready" && "READY TO SUBMIT"}
            {status === "not-ready" && `NOT READY · ${result.blocking} blocking`}
            {status === "inconclusive" && `INCONCLUSIVE · ${result.skipped} check(s) did not run`}
          </div>
          <div className="panel-list">
            {result.checks.map((check, i) => (
              <div className="gate-check" key={i}>
                <span style={{ marginTop: 2 }}>
                  {check.status === "pass" && <CheckCircleIcon size={14} />}
                  {check.status === "fail" && <ErrorIcon size={14} />}
                  {check.status === "skip" && <SkipCircleIcon size={14} />}
                </span>
                <div>
                  <div className="gate-check__label">{check.label}</div>
                  {(check.status !== "pass" || check.count > 0) && (
                    <div className="gate-check__meta">
                      {check.status === "skip"
                        ? "did not run"
                        : check.count > 0
                          ? `${check.count} issue${check.count === 1 ? "" : "s"}${check.blocking ? " · blocking" : ""}`
                          : ""}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
