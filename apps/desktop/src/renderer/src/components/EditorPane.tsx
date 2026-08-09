import { useEffect, useRef } from "react";
import * as monaco from "monaco-editor";
import type { ModelRegistry } from "../editor/modelRegistry";

interface EditorPaneProps {
  activeUri: string | null;
  registry: ModelRegistry;
  onContentChange: (uri: string, content: string) => void;
  onSaveRequested: () => void;
  /** Line to reveal and select on the next model switch — set by "click to jump" callers. */
  revealTarget: { uri: string; line: number } | null;
}

/**
 * A single persistent Monaco instance. Swapping `activeUri` calls `setModel`, not remount
 * — remounting would create a fresh undo stack and lose scroll position on every tab
 * click, which is the one thing an editor must never do.
 */
export default function EditorPane({
  activeUri,
  registry,
  onContentChange,
  onSaveRequested,
  revealTarget,
}: EditorPaneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const wiredModels = useRef(new Set<string>());
  const onContentChangeRef = useRef(onContentChange);
  onContentChangeRef.current = onContentChange;

  useEffect(() => {
    if (!hostRef.current) return;
    const editor = monaco.editor.create(hostRef.current, {
      theme: "aurelius-dark",
      automaticLayout: true,
      fontSize: 13.5,
      fontFamily: "var(--font-mono)",
      minimap: { enabled: true, maxColumn: 80 },
      renderLineHighlight: "all",
      cursorBlinking: "smooth",
      smoothScrolling: true,
      scrollBeyondLastLine: false,
      wordWrap: "on",
      padding: { top: 12 },
    });
    editorRef.current = editor;

    editor.addAction({
      id: "aurelius.save",
      label: "Save",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS],
      run: () => onSaveRequested(),
    });

    return () => editor.dispose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;

    if (!activeUri) {
      editor.setModel(null);
      return;
    }
    const model = registry.get(activeUri);
    if (!model) return;

    if (editor.getModel() !== model) {
      editor.setModel(model);
    }

    if (!wiredModels.current.has(activeUri)) {
      wiredModels.current.add(activeUri);
      model.onDidChangeContent(() => {
        const uri = registry.uriOf(model);
        if (uri) onContentChangeRef.current(uri, model.getValue());
      });
    }

    editor.focus();
  }, [activeUri, registry]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || !revealTarget || revealTarget.uri !== activeUri) return;
    const line = revealTarget.line + 1;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 });
  }, [revealTarget, activeUri]);

  return <div ref={hostRef} className="editorarea__editor" />;
}
