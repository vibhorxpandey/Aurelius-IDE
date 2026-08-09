import type { UserProfile } from "../state/profile";
import { avatarColour, initials } from "../state/profile";
import type { ServerStatus } from "@shared/lsp-types";
import { CloseIcon } from "./icons";

interface ProfilePanelProps {
  profile: UserProfile;
  onSignOut: () => void;
  onClose: () => void;
  serverStatus: ServerStatus | null;
  stats: {
    filesOpen: number;
    errors: number;
    warnings: number;
    filesAnalyzed: number;
  };
}

/**
 * Real numbers, not filler. Every figure here reads off state the rest of the app already
 * computes from live LSP diagnostics — there is no separate "profile stats" data source
 * to drift out of sync with what's actually on screen.
 */
export default function ProfilePanel({ profile, onSignOut, onClose, serverStatus, stats }: ProfilePanelProps) {
  return (
    <div className="profile-panel">
      <div className="profile-panel__header">
        <span>Account</span>
        <span className="sidebar-refresh" onClick={onClose}>
          <CloseIcon size={14} />
        </span>
      </div>

      <div className="profile-panel__identity">
        <div className="profile-panel__avatar" style={{ background: avatarColour(profile.name) }}>
          {initials(profile.name)}
        </div>
        <div className="profile-panel__name">{profile.name}</div>
        {profile.institution && <div className="profile-panel__institution">{profile.institution}</div>}
        {profile.email && <div className="profile-panel__email">{profile.email}</div>}
      </div>

      <div className="profile-panel__section">This session</div>
      <div className="profile-panel__stats">
        <StatRow label="Files open" value={stats.filesOpen} />
        <StatRow label="Errors found" value={stats.errors} tone={stats.errors > 0 ? "error" : undefined} />
        <StatRow label="Warnings found" value={stats.warnings} tone={stats.warnings > 0 ? "warn" : undefined} />
        <StatRow label="Files analyzed" value={stats.filesAnalyzed} />
      </div>

      <div className="profile-panel__section">Language server</div>
      <div className="profile-panel__server">
        <span className="statusbar__dot" style={{ background: serverStatus?.state === "running" ? "#3fb950" : "#f14c4c" }} />
        <span>{serverStatus?.state ?? "unknown"}</span>
      </div>

      <button className="profile-panel__signout" onClick={onSignOut}>
        Sign out
      </button>
      <p className="login__note" style={{ marginTop: 10 }}>
        Local profile — sign-out just clears it from this machine.
      </p>
    </div>
  );
}

function StatRow({ label, value, tone }: { label: string; value: number; tone?: "error" | "warn" }) {
  return (
    <div className="profile-panel__stat-row">
      <span>{label}</span>
      <span className={tone === "error" ? "stat-error" : tone === "warn" ? "stat-warn" : undefined}>{value}</span>
    </div>
  );
}
