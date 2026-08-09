import * as monaco from "monaco-editor";
import type { LspDiagnostic } from "@shared/lsp-types";

const SEVERITY: Record<LspDiagnostic["severity"], monaco.MarkerSeverity> = {
  1: monaco.MarkerSeverity.Error,
  2: monaco.MarkerSeverity.Warning,
  3: monaco.MarkerSeverity.Info,
  4: monaco.MarkerSeverity.Hint,
};

export function toMarker(d: LspDiagnostic): monaco.editor.IMarkerData {
  const startColumn = d.range.start.character + 1;
  const endColumn = d.range.end.character + 1;
  return {
    severity: SEVERITY[d.severity] ?? monaco.MarkerSeverity.Warning,
    startLineNumber: d.range.start.line + 1,
    startColumn,
    endLineNumber: d.range.end.line + 1,
    // A zero-width range (a single-character finding like AUR008) must still render a
    // visible squiggle rather than collapsing to nothing.
    endColumn: endColumn > startColumn ? endColumn : startColumn + 1,
    message: d.message,
    code: d.code,
    source: d.source,
  };
}

export function applyDiagnostics(model: monaco.editor.ITextModel, diagnostics: LspDiagnostic[]): void {
  monaco.editor.setModelMarkers(model, "aurelius", diagnostics.map(toMarker));
}
