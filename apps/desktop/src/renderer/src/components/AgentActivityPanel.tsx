import type { ActivityEvent, ActivityKind } from "../state/activity";

interface AgentActivityPanelProps {
  events: ActivityEvent[];
}

const KIND_LOOK: Record<ActivityKind, { icon: string; colour: string; label: string }> = {
  connect: { icon: "●", colour: "#3fb950", label: "Connection" },
  structural: { icon: "⚡", colour: "var(--sev-info)", label: "Structural pass" },
  verified: { icon: "🔎", colour: "#4ec9b0", label: "Verification pass" },
  gate: { icon: "🚦", colour: "var(--fg-default)", label: "Submission gate" },
  search: { icon: "🔍", colour: "var(--fg-default)", label: "Literature search" },
  error: { icon: "✕", colour: "var(--sev-error)", label: "Error" },
};

/**
 * Every entry here is derived from a real event the client actually received — a
 * publishDiagnostics batch, a status change, a gate run — not a scripted animation. The
 * distinction between "structural pass" and "verification pass" is read off which
 * diagnostic codes are present in the batch (AUR002/003/004 are network-only), which is
 * the same two-phase split documented in ARCHITECTURE.md § 4, made visible rather than
 * asserted.
 */
export default function AgentActivityPanel({ events }: AgentActivityPanelProps) {
  if (events.length === 0) {
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
