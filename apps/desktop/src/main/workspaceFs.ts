/** Minimal filesystem surface for the explorer and editor — read/write/list, nothing more. */
import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { join } from "node:path";
import type { FsEntry } from "../shared/lsp-types";

export async function listDirectory(path: string): Promise<FsEntry[]> {
  const entries = await readdir(path, { withFileTypes: true });
  return entries
    .filter((e) => !e.name.startsWith(".") && e.name !== "__pycache__")
    .map((e) => ({
      name: e.name,
      path: join(path, e.name),
      isDirectory: e.isDirectory(),
    }))
    .sort((a, b) => {
      if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
}

export async function readTextFile(path: string): Promise<string> {
  return readFile(path, "utf-8");
}

export async function writeTextFile(path: string, content: string): Promise<void> {
  await writeFile(path, content, "utf-8");
}

export async function isDirectory(path: string): Promise<boolean> {
  const s = await stat(path);
  return s.isDirectory();
}
