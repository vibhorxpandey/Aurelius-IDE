import { FileTexIcon, FileBibIcon, FileGenericIcon, CloseIcon } from "./icons";
import type { EditorTab } from "../state/types";

interface TabBarProps {
  tabs: EditorTab[];
  activeUri: string | null;
  onSelect: (uri: string) => void;
  onClose: (uri: string) => void;
}

function iconFor(language: EditorTab["language"]) {
  if (language === "latex") return FileTexIcon;
  if (language === "bibtex") return FileBibIcon;
  return FileGenericIcon;
}

export default function TabBar({ tabs, activeUri, onSelect, onClose }: TabBarProps) {
  if (tabs.length === 0) return null;
  return (
    <div className="tabbar">
      {tabs.map((tab) => {
        const Icon = iconFor(tab.language);
        return (
          <div
            key={tab.uri}
            className="tab"
            data-active={tab.uri === activeUri}
            onClick={() => onSelect(tab.uri)}
            onMouseDown={(e) => {
              if (e.button === 1) {
                e.preventDefault();
                onClose(tab.uri);
              }
            }}
            title={tab.path}
          >
            <Icon size={15} />
            {tab.dirty && <span className="tab__dirty-dot" title="Unsaved changes" />}
            <span className="tab__name">{tab.name}</span>
            <span
              className="tab__close"
              onClick={(e) => {
                e.stopPropagation();
                onClose(tab.uri);
              }}
            >
              <CloseIcon size={13} />
            </span>
          </div>
        );
      })}
    </div>
  );
}
