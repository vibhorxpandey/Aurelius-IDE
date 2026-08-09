/**
 * Runs inside Electron in normal use. `isElectron` is false only when this renderer is
 * loaded directly in a browser (Vite's dev server, or a screenshot tool) with no preload
 * bridge — there the app still renders its layout with static demo content, but every real
 * operation (file I/O, the language server) is unavailable and says so rather than faking
 * a result.
 */
import type { AureliusApi, FsEntry } from "@shared/lsp-types";

export const isElectron = typeof window !== "undefined" && !!window.aurelius;

const DEMO_PAPER = `\\documentclass[11pt]{article}
\\usepackage{natbib}
\\title{Hybrid Retrieval for Indian Equity Filings}
\\begin{document}
\\maketitle

\\begin{abstract}
We present a hybrid retrieval system. Studies show that dense retrieval
underperforms on numerical tables.
\\end{abstract}

\\section{Introduction}
Sparse retrieval remains competitive on out-of-domain data \\citep{thakur2021beir}.
Reciprocal rank fusion improves recall by 12\\% over single-retriever baselines.
\\end{document}
`;

const mockFiles: Record<string, string> = {
  "/demo-workspace/paper.tex": DEMO_PAPER,
  "/demo-workspace/references.bib":
    "@article{thakur2021beir,\n  author = {Thakur, Nandan},\n  title = {BEIR},\n  year = {2021}\n}\n",
};

/** A read-only stand-in used only when there is no Electron preload bridge. */
const mockApi: AureliusApi = {
  workspace: {
    defaultPath: async () => "/demo-workspace",
    list: async (path: string): Promise<FsEntry[]> => {
      if (path !== "/demo-workspace") return [];
      return [
        { name: "paper.tex", path: "/demo-workspace/paper.tex", isDirectory: false },
        { name: "references.bib", path: "/demo-workspace/references.bib", isDirectory: false },
      ];
    },
    read: async (path: string) => mockFiles[path] ?? "",
    write: async () => {
      throw new Error("Read-only preview (not running inside Electron)");
    },
    isDirectory: async (path: string) => path === "/demo-workspace",
    openFolderDialog: async () => null,
  },
  lsp: {
    send: () => {},
    restart: async () => {},
    onMessage: () => () => {},
    onStatus: (handler) => {
      handler({
        state: "not-found",
        detail: "Preview mode — open this app in Electron for a live language server.",
      });
      return () => {};
    },
    onStderr: () => () => {},
  },
};

export function getApi(): AureliusApi {
  return window.aurelius ?? mockApi;
}
