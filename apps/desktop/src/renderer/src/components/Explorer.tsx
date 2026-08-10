import { useEffect, useRef, useState } from "react";
import type { FsEntry } from "@shared/lsp-types";
import { getApi } from "../platform";
import {
  ChevronIcon,
  FolderIcon,
  FileTexIcon,
  FileBibIcon,
  FileMermaidIcon,
  FileGenericIcon,
  NewFileIcon,
  NewFolderIcon,
  RefreshIcon,
} from "./icons";

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

function join(dir: string, name: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return dir.endsWith(sep) ? dir + name : dir + sep + name;
}

/**
 * New File / New Folder create real filesystem entries via IPC (`workspace:create-file`,
 * `workspace:create-folder`, both refusing to overwrite) — not a client-side-only tree
 * mutation. Refreshing after creation is a full re-list rather than an optimistic local
 * insert, so what's on screen always matches what's actually on disk.
 */
export default function Explorer({ rootPath, activePath, onOpenFile }: ExplorerProps) {
  const [rootLabel] = useState(() => rootPath.split(/[\\/]/).filter(Boolean).pop() ?? rootPath);
  const [refreshKey, setRefreshKey] = useState(0);
  const [creating, setCreating] = useState<"file" | "folder" | null>(null);

  const refresh = () => setRefreshKey((k) => k + 1);

  const submitCreate = async (name: string) => {
    const trimmed = name.trim();
    setCreating(null);
    if (!trimmed) return;
    const path = join(rootPath, trimmed);
    try {
      if (creating === "file") {
        await getApi().workspace.createFile(path);
        refresh();
        onOpenFile(path);
      } else if (creating === "folder") {
        await getApi().workspace.createFolder(path);
        refresh();
      }
    } catch (err) {
      console.error("Could not create", path, err);
    }
  };

  return (
    <div>
      <div className="sidebar-section">
        <span>{rootLabel}</span>
        <span className="explorer-actions">
          <span title="New File" onClick={() => setCreating("file")}>
            <NewFileIcon size={14} />
          </span>
          <span title="New Folder" onClick={() => setCreating("folder")}>
            <NewFolderIcon size={14} />
          </span>
          <span title="Refresh" onClick={refresh}>
            <RefreshIcon size={13} />
          </span>
        </span>
      </div>
      {creating && (
        <InlineCreateRow
          placeholder={creating === "file" ? "filename.tex" : "folder name"}
          onSubmit={submitCreate}
          onCancel={() => setCreating(null)}
        />
      )}
      <DirectoryNode
        key={refreshKey}
        path={rootPath}
        depth={0}
        activePath={activePath}
        onOpenFile={onOpenFile}
        forceOpen
      />
    </div>
  );
}

function InlineCreateRow({
  placeholder,
  onSubmit,
  onCancel,
}: {
  placeholder: string;
  onSubmit: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => inputRef.current?.focus(), []);

  return (
    <div className="tree-row" style={{ paddingLeft: 20 }}>
      <input
        ref={inputRef}
        className="tree-create-input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => onSubmit(value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSubmit(value);
          if (e.key === "Escape") onCancel();
        }}
      />
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
