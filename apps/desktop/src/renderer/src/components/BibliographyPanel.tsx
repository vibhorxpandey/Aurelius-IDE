import { useEffect, useState } from "react";
import type { BibliographyStatus } from "@shared/lsp-types";
import type { LspClient } from "../lsp/client";
import { RefreshIcon } from "./icons";

interface BibliographyPanelProps {
  client: LspClient | null;
  activeUri: string | null;
  /** Bumped whenever diagnostics land, so the panel re-fetches without polling. */
  refreshToken: number;
  onReveal: (bibUri: string, line: number) => void;
}

const SEVERITY_RANK: Record<string, number> = {
  retracted: 0,
  not_found: 1,
  unverified: 2,
  unchecked: 3,
  verified: 4,
};

const BADGE_LABEL: Record<string, string> = {
  retracted: "RETRACTED",
  not_found: "not found",
  unverified: "unverified",
  unchecked: "unchecked",
  verified: "verified",
};

export default function BibliographyPanel({
  client,
  activeUri,
  refreshToken,
  onReveal,
}: BibliographyPanelProps) {
  const [status, setStatus] = useState<BibliographyStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!client || !activeUri) {
      setStatus(null);
      return;
    }
    setLoading(true);
    try {
      const result = await client.executeCommand<BibliographyStatus>(
        "aurelius.bibliographyStatus",
        [activeUri]
      );
      setStatus(result);
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    void load();
  }, [client, activeUri, refreshToken]);

  if (!client) {
    return <div className="sidebar__empty">Language server unavailable.</div>;
  }
  if (!activeUri) {
    return <div className="sidebar__empty">Open a .tex file to see its bibliography.</div>;
  }
  if (!status || loading) {
    return <div className="sidebar__empty">Loading…</div>;
  }
  if (!status.ok) {
    return <div className="sidebar__empty">{status.reason ?? "No analysis yet."}</div>;
  }
  if (status.entries.length === 0) {
    return <div className="sidebar__empty">No bibliography entries found for this paper.</div>;
  }

  const sorted = [...status.entries].sort((a, b) => {
    const rank = (SEVERITY_RANK[a.verdict] ?? 9) - (SEVERITY_RANK[b.verdict] ?? 9);
    return rank !== 0 ? rank : a.key.localeCompare(b.key);
  });

  const problems = (status.counts.retracted ?? 0) + (status.counts.not_found ?? 0) + (status.counts.unverified ?? 0);

  return (
    <div>
      <div className="sidebar-section">
        <span>
          {status.entries.length} references
          {problems > 0 ? ` · ${problems} problem${problems === 1 ? "" : "s"}` : ""}
        </span>
        <span className="sidebar-refresh" onClick={() => void load()} title="Refresh">
          <RefreshIcon size={13} />
        </span>
      </div>
      <div className="panel-list">
        {sorted.map((entry) => (
          <div
            key={entry.key}
            className="biblio-entry"
            data-severity={entry.verdict}
            onClick={() => status.bibUri && onReveal(status.bibUri, entry.bibLine)}
          >
            <div className="biblio-entry__head">
              <span className="biblio-entry__key">{entry.key}</span>
              <span className="biblio-entry__badge" data-severity={entry.verdict}>
                {BADGE_LABEL[entry.verdict] ?? entry.verdict}
              </span>
              {entry.citeCount === 0 && (
                <span className="biblio-entry__badge" data-severity="unchecked">
                  uncited
                </span>
              )}
            </div>
            {entry.title && <div className="biblio-entry__title">{entry.title}</div>}
            <div className="biblio-entry__meta">
              {[entry.author, entry.year, entry.venue].filter(Boolean).join(" · ") || entry.entryType}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
