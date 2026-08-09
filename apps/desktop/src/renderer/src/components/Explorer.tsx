import { useEffect, useState } from "react";
import type { FsEntry } from "@shared/lsp-types";
import { getApi } from "../platform";
import { ChevronIcon, FolderIcon, FileTexIcon, FileBibIcon, FileMermaidIcon, FileGenericIcon } from "./icons";

interface ExplorerProps {
  rootPath: string;
  activePath: string | null;
  onOpenFile: (path: string) => void;
}

function iconFor(name: string) {
  if (name.endsWith(".tex") || name.endsWith(".ltx")) return FileTexIcon;
  if (name.endsWith(".bib")) return FileBibIcon;
  if (name.endsWith(".mmd") || name.endsWith(".mermaid")) return FileMermaidIcon;
  return FileGenericIcon;
}

export default function Explorer({ rootPath, activePath, onOpenFile }: ExplorerProps) {
  const [rootLabel] = useState(() => rootPath.split(/[\\/]/).filter(Boolean).pop() ?? rootPath);

  return (
    <div>
      <div className="sidebar-section">
        <span>{rootLabel}</span>
      </div>
      <DirectoryNode path={rootPath} depth={0} activePath={activePath} onOpenFile={onOpenFile} forceOpen />
    </div>
  );
}

function DirectoryNode({
  path,
  depth,
  activePath,
  onOpenFile,
  forceOpen,
}: {
  path: string;
  depth: number;
  activePath: string | null;
  onOpenFile: (path: string) => void;
  forceOpen?: boolean;
}) {
  const [open, setOpen] = useState(!!forceOpen);
  const [entries, setEntries] = useState<FsEntry[] | null>(null);

  useEffect(() => {
    if (!open || entries !== null) return;
    let cancelled = false;
    getApi()
      .workspace.list(path)
      .then((result) => {
        if (!cancelled) setEntries(result);
      })
      .catch(() => {
        if (!cancelled) setEntries([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, path, entries]);

  return (
    <div>
      {!forceOpen && (
        <div
          className="tree-row"
          style={{ paddingLeft: 4 + depth * 12 }}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="tree-row__chevron" data-open={open}>
            <ChevronIcon size={12} />
          </span>
          <FolderIcon size={16} className="tree-row__icon" />
          <span className="tree-row__name">{path.split(/[\\/]/).filter(Boolean).pop()}</span>
        </div>
      )}
      {open &&
        entries?.map((entry) =>
          entry.isDirectory ? (
            <DirectoryNode
              key={entry.path}
              path={entry.path}
              depth={depth + 1}
              activePath={activePath}
              onOpenFile={onOpenFile}
            />
          ) : (
            <FileNode
              key={entry.path}
              entry={entry}
              depth={depth + 1}
              active={activePath === entry.path}
              onOpenFile={onOpenFile}
            />
          )
        )}
    </div>
  );
}

function FileNode({
  entry,
  depth,
  active,
  onOpenFile,
}: {
  entry: FsEntry;
  depth: number;
  active: boolean;
  onOpenFile: (path: string) => void;
}) {
  const Icon = iconFor(entry.name);
  return (
    <div
      className="tree-row"
      data-selected={active}
      style={{ paddingLeft: 20 + depth * 12 }}
      onClick={() => onOpenFile(entry.path)}
    >
      <Icon size={16} className="tree-row__icon" />
      <span className="tree-row__name">{entry.name}</span>
    </div>
  );
}
