export type EditorLanguage = "latex" | "bibtex" | "mermaid" | "plaintext";

export interface EditorTab {
  uri: string;
  path: string;
  name: string;
  language: EditorLanguage;
  dirty: boolean;
}

export function detectLanguage(path: string): EditorLanguage {
  if (/\.(tex|ltx)$/i.test(path)) return "latex";
  if (/\.bib$/i.test(path)) return "bibtex";
  if (/\.(mmd|mermaid)$/i.test(path)) return "mermaid";
  return "plaintext";
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}
