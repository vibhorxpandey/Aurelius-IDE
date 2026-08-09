/**
 * Monaco ships no LaTeX or BibTeX language — its `basic-languages` bundle covers roughly
 * seventy languages and none of them are this one. These are Monarch tokenizers, not full
 * grammars: good enough for commands, comments, braces, math and BibTeX fields to read
 * correctly, which is what a prototype needs. The real analysis comes from the language
 * server's diagnostics, not from the highlighter.
 */
import * as monaco from "monaco-editor";

export function registerLanguages(): void {
  registerLatex();
  registerBibtex();
  registerMermaid();
  defineAureliusTheme();
}

function registerLatex(): void {
  monaco.languages.register({ id: "latex", extensions: [".tex", ".ltx"], aliases: ["LaTeX"] });

  monaco.languages.setLanguageConfiguration("latex", {
    comments: { lineComment: "%" },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "$", close: "$" },
    ],
  });

  monaco.languages.setMonarchTokensProvider("latex", {
    defaultToken: "",
    tokenizer: {
      root: [
        [/%.*$/, "comment"],
        [/\\[a-zA-Z]+\*?/, "keyword"],
        [/\\[^a-zA-Z]/, "keyword"], // escaped punctuation: \%, \&, \\, ...
        [/\$\$/, { token: "string", next: "@mathblock" }],
        [/\$/, { token: "string", next: "@mathinline" }],
        [/[{}]/, "delimiter.curly"],
        [/[[\]]/, "delimiter.square"],
      ],
      mathinline: [
        [/\$/, { token: "string", next: "@pop" }],
        [/[^$]+/, "string"],
      ],
      mathblock: [
        [/\$\$/, { token: "string", next: "@pop" }],
        [/[^$]+/, "string"],
      ],
    },
  });
}

function registerBibtex(): void {
  monaco.languages.register({ id: "bibtex", extensions: [".bib"], aliases: ["BibTeX"] });

  monaco.languages.setLanguageConfiguration("bibtex", {
    brackets: [
      ["{", "}"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: '"', close: '"' },
    ],
  });

  monaco.languages.setMonarchTokensProvider("bibtex", {
    defaultToken: "",
    tokenizer: {
      root: [
        [/%.*$/, "comment"],
        [/@[a-zA-Z]+/, "type"],
        [/[a-zA-Z][\w-]*(?=\s*=)/, "attribute.name"],
        [/=/, "operator"],
        [/[{}]/, "delimiter.curly"],
        [/".*?"/, "string"],
        [/\d{4}\b/, "number"],
      ],
    },
  });
}

function registerMermaid(): void {
  monaco.languages.register({ id: "mermaid", extensions: [".mmd", ".mermaid"], aliases: ["Mermaid"] });

  monaco.languages.setLanguageConfiguration("mermaid", {
    comments: { lineComment: "%%" },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
  });

  monaco.languages.setMonarchTokensProvider("mermaid", {
    defaultToken: "",
    keywords: [
      "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram",
      "gantt", "pie", "subgraph", "end", "participant", "loop", "alt", "else", "opt",
      "TB", "TD", "BT", "RL", "LR", "style", "classDef", "class",
    ],
    tokenizer: {
      root: [
        [/%%.*$/, "comment"],
        [/-->|--x|--o|->>|-->>|-\.->|==>/, "keyword"],
        [/\|[^|]*\|/, "string"],
        [/\[\(.*?\)\]|\(\(.*?\)\)|\[\[.*?\]\]/, "type"],
        [/[a-zA-Z_]\w*/, { cases: { "@keywords": "keyword", "@default": "identifier" } }],
        [/["'].*?["']/, "string"],
        [/[{}[\]()]/, "delimiter.curly"],
      ],
    },
  });
}

/**
 * A VS Code Dark+ approximation. Not pulled from `vscode-textmate`/theme JSON, because
 * bringing in a full TextMate grammar pipeline for a prototype's colour scheme is exactly
 * the kind of scope creep that turns a demo into the thing the roadmap already warned
 * against building from scratch (Electron+Monaco, "12+ months before it feels like an
 * IDE"). This is a palette match, not a rebuild.
 */
function defineAureliusTheme(): void {
  monaco.editor.defineTheme("aurelius-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "6a9955", fontStyle: "italic" },
      { token: "keyword", foreground: "569cd6" },
      { token: "string", foreground: "ce9178" },
      { token: "delimiter.curly", foreground: "d4d4d4" },
      { token: "delimiter.square", foreground: "d4d4d4" },
      { token: "type", foreground: "4ec9b0" },
      { token: "attribute.name", foreground: "9cdcfe" },
      { token: "number", foreground: "b5cea8" },
      { token: "operator", foreground: "d4d4d4" },
    ],
    colors: {
      "editor.background": "#1e1e1e",
      "editorLineNumber.foreground": "#5a5a5a",
      "editorLineNumber.activeForeground": "#c6c6c6",
    },
  });
}
