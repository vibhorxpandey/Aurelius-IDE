import { ExplorerIcon, BookIcon, GateIcon, DiagramIcon, PlayIcon, ActivityIcon, ExtensionsIcon } from "./icons";

export type ActivityView =
  | "explorer"
  | "bibliography"
  | "gate"
  | "diagrams"
  | "run"
  | "agent"
  | "extensions";

interface ActivityBarProps {
  active: ActivityView;
  onChange: (view: ActivityView) => void;
  bibliographyProblems: number;
  gateBlocking: number;
  profileName?: string;
  profileColour?: string;
  profileInitials?: string;
  profileActive?: boolean;
  onProfileClick?: () => void;
}

const ITEMS: { id: ActivityView; label: string; Icon: typeof ExplorerIcon }[] = [
  { id: "explorer", label: "Explorer", Icon: ExplorerIcon },
  { id: "bibliography", label: "Bibliography", Icon: BookIcon },
  { id: "gate", label: "Submission Gate", Icon: GateIcon },
  { id: "diagrams", label: "Architecture & Diagrams", Icon: DiagramIcon },
  { id: "run", label: "Run and Debug", Icon: PlayIcon },
  { id: "agent", label: "Agent Activity", Icon: ActivityIcon },
  { id: "extensions", label: "Extensions", Icon: ExtensionsIcon },
];

export default function ActivityBar({
  active,
  onChange,
  bibliographyProblems,
  gateBlocking,
  profileName,
  profileColour,
  profileInitials,
  profileActive,
  onProfileClick,
}: ActivityBarProps) {
  return (
    <div className="activitybar">
      <div>
        {ITEMS.map(({ id, label, Icon }) => {
          const badge = id === "bibliography" ? bibliographyProblems : id === "gate" ? gateBlocking : 0;
          return (
            <div
              key={id}
              className="activitybar__item"
              data-active={active === id}
              title={label}
              onClick={() => onChange(id)}
            >
              <Icon size={20} />
              {badge > 0 && <span className="activitybar__badge">{badge > 99 ? "99+" : badge}</span>}
            </div>
          );
        })}
      </div>
      {profileName && (
        <div className="activitybar__footer">
          <div
            className="activitybar__profile"
            data-active={profileActive}
            title={profileName}
            onClick={onProfileClick}
          >
            <span className="activitybar__avatar" style={{ background: profileColour }}>
              {profileInitials}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
