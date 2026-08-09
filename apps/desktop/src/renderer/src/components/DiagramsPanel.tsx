import { useEffect, useState } from "react";
import type { FsEntry } from "@shared/lsp-types";
import { getApi } from "../platform";
import { FileMermaidIcon } from "./icons";

interface DiagramsPanelProps {
  rootPath: string;
  activePath: string | null;
  onOpenFile: (path: string) => void;
}

/** Lists Mermaid diagrams in the workspace. Opening one shows a live source + preview split. */
export default function DiagramsPanel({ rootPath, activePath, onOpenFile }: DiagramsPanelProps) {
  const [files, setFiles] = useState<FsEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getApi()
      .workspace.list(rootPath)
      .then((entries) => {
        if (!cancelled) setFiles(entries.filter((e) => !e.isDirectory && /\.(mmd|mermaid)$/i.test(e.name)));
      })
      .catch(() => !cancelled && setFiles([]));
    return () => {
      cancelled = true;
    };
  }, [rootPath]);

  return (
    <div>
      <div className="sidebar-section">
        <span>Architecture &amp; diagrams</span>
      </div>
      {files === null ? (
        <div className="sidebar__empty">Loading…</div>
      ) : files.length === 0 ? (
        <div className="sidebar__empty">
          No .mmd diagram files in this workspace. Create one and it will show a live
          Mermaid preview alongside the source.
        </div>
      ) : (
        files.map((file) => (
          <div
            key={file.path}
            className="tree-row"
            data-selected={activePath === file.path}
            style={{ paddingLeft: 20 }}
            onClick={() => onOpenFile(file.path)}
          >
            <FileMermaidIcon size={16} className="tree-row__icon" />
            <span className="tree-row__name">{file.name}</span>
          </div>
        ))
      )}
    </div>
  );
}
