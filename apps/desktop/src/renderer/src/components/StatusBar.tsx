import type { ServerStatus } from "@shared/lsp-types";
import { ErrorIcon, WarningIcon, RefreshIcon } from "./icons";

interface StatusBarProps {
  serverStatus: ServerStatus | null;
  errors: number;
  warnings: number;
  activeLanguage: string | null;
  onRestartServer: () => void;
}

const STATE_COLOUR: Record<ServerStatus["state"], string> = {
  starting: "#cca700",
  running: "#3fb950",
  crashed: "#f14c4c",
  "not-found": "#f14c4c",
};

const STATE_LABEL: Record<ServerStatus["state"], string> = {
  starting: "Starting language server…",
  running: "aurelius-lsp",
  crashed: "Server crashed",
  "not-found": "Server unavailable",
};

export default function StatusBar({
  serverStatus,
  errors,
  warnings,
  activeLanguage,
  onRestartServer,
}: StatusBarProps) {
  const state = serverStatus?.state ?? "starting";
  return (
    <div className="shell__statusbar">
      <div className="statusbar__group">
        <div
          className="statusbar__item"
          data-clickable={state !== "running"}
          onClick={state !== "running" ? onRestartServer : undefined}
          title={serverStatus?.detail ?? ""}
        >
          {state === "starting" ? (
            <RefreshIcon size={13} />
          ) : (
            <span className="statusbar__dot" style={{ background: STATE_COLOUR[state] }} />
          )}
          <span>{STATE_LABEL[state]}</span>
        </div>
        <div className="statusbar__item">
          <ErrorIcon size={13} />
          <span>{errors}</span>
          <WarningIcon size={13} />
          <span>{warnings}</span>
        </div>
      </div>
      <div className="statusbar__spacer" />
      <div className="statusbar__group">
        {activeLanguage && <div className="statusbar__item">{activeLanguage}</div>}
        <div className="statusbar__item">UTF-8</div>
      </div>
    </div>
  );
}
