export type EditorLanguage = "latex" | "bibtex" | "plaintext";

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
  return "plaintext";
}

export function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}
