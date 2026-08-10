import type { ActivityEvent, ActivityKind } from "../state/activity";
import type { VerificationProgressEvent } from "../lsp/client";

interface AgentActivityPanelProps {
  events: ActivityEvent[];
  /** Citation key -> the real cascade steps seen for it so far, live, mid-verification. */
  liveProgress: Map<string, VerificationProgressEvent[]>;
}

const KIND_LOOK: Record<ActivityKind, { icon: string; colour: string; label: string }> = {
  connect: { icon: "●", colour: "#3fb950", label: "Connection" },
  structural: { icon: "⚡", colour: "var(--sev-info)", label: "Structural pass" },
  verified: { icon: "🔎", colour: "#4ec9b0", label: "Verification pass" },
  gate: { icon: "🚦", colour: "var(--fg-default)", label: "Submission gate" },
  build: { icon: "📄", colour: "var(--fg-default)", label: "Compile" },
  search: { icon: "🔍", colour: "var(--fg-default)", label: "Literature search" },
  error: { icon: "✕", colour: "var(--sev-error)", label: "Error" },
};

/** The real, fixed order `aurelius-mcp`'s verify_citation queries indexes in — not a
 * guess, this is the same list `CLAUDE.md` and `ARCHITECTURE.md` document. */
const CASCADE_STEPS: { id: string; label: string }[] = [
  { id: "openalex", label: "OpenAlex" },
  { id: "crossref", label: "Crossref" },
  { id: "arxiv", label: "arXiv" },
  { id: "semantic_scholar", label: "Semantic Scholar" },
];

const EXTRA_LABELS: Record<string, string> = { web_fallback: "Web fallback" };

function StepTracker({ citationKey, events }: { citationKey: string; events: VerificationProgressEvent[] }) {
  const bySource = new Map(events.map((e) => [e.source, e.status]));
  const extra = events
    .map((e) => e.source)
    .filter((s) => !CASCADE_STEPS.some((step) => step.id === s))
    .filter((s, i, arr) => arr.indexOf(s) === i)
    .map((id) => ({ id, label: EXTRA_LABELS[id] ?? id }));
  const steps = [...CASCADE_STEPS, ...extra];

  return (
    <div className="search-progress__item">
      <div className="search-progress__key">Verifying '{citationKey}'</div>
      <div className="search-progress__steps">
        {steps.map((step, i) => {
          const status = bySource.get(step.id) ?? "pending";
          return (
            <div className="search-progress__step-wrap" key={step.id}>
              <div className="search-progress__step" data-state={status}>
                <span className="search-progress__step-dot" />
                <span className="search-progress__step-label">{step.label}</span>
              </div>
              {i < steps.length - 1 && <span className="search-progress__arrow">→</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Every entry here is derived from a real event the client actually received — a
 * publishDiagnostics batch, a status change, a gate run — not a scripted animation. The
 * distinction between "structural pass" and "verification pass" is read off which
 * diagnostic codes are present in the batch (AUR002/003/004 are network-only), which is
 * the same two-phase split documented in ARCHITECTURE.md § 4, made visible rather than
 * asserted. `liveProgress` is the same idea one level deeper: real per-source progress
 * from `aurelius/verificationProgress`, not a staged sequence — a source the cascade
 * never reaches (an earlier one already matched) simply never lights up.
 */
export default function AgentActivityPanel({ events, liveProgress }: AgentActivityPanelProps) {
  if (events.length === 0 && liveProgress.size === 0) {
    return (
      <div className="sidebar__empty">
        Nothing yet — open a file to see the analysis engine work in real time.
      </div>
    );
  }

  return (
    <div>
      <div className="sidebar-section">
        <span>Live agent activity</span>
      </div>

      {liveProgress.size > 0 && (
        <div className="search-progress">
          {Array.from(liveProgress.entries()).map(([key, ev]) => (
            <StepTracker key={key} citationKey={key} events={ev} />
          ))}
        </div>
      )}

      <div className="activity-feed">
        {events
          .slice()
          .reverse()
          .map((event) => {
            const look = KIND_LOOK[event.kind];
            return (
              <div className="activity-item" key={event.id}>
                <div className="activity-item__head">
                  <span style={{ color: look.colour }}>{look.icon}</span>
                  <span className="activity-item__title">{event.title}</span>
                  <span className="activity-item__time">
                    {new Date(event.time).toLocaleTimeString([], { hour12: false })}
                  </span>
                </div>
                {event.details.length > 0 && (
                  <ul className="activity-item__details">
                    {event.details.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
