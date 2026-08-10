/** Filesystem surface for the explorer, editor, and PDF preview. */
import { readdir, readFile, writeFile, stat, mkdir, open, copyFile } from "node:fs/promises";
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

/**
 * Returns the file as base64 rather than a raw Buffer — Electron IPC can carry binary
 * data structurally-cloned, but base64 over the existing string-shaped channel needs no
 * new serialisation path and is simple to reason about for a file the size of a compiled
 * PDF (tens of kilobytes, not gigabytes).
 */
export async function readBinaryFileBase64(path: string): Promise<string> {
  const buffer = await readFile(path);
  return buffer.toString("base64");
}

export async function createFile(path: string): Promise<void> {
  // "wx": create-exclusive. Refuses to overwrite an existing file — creating a file that
  // already exists is very likely a mistake (a stale tree, a name collision), and
  // silently truncating someone's paper is exactly the kind of destructive default this
  // project's own conventions warn against.
  const handle = await open(path, "wx");
  await handle.close();
}

export async function createFolder(path: string): Promise<void> {
  await mkdir(path, { recursive: false });
}

/** Backs the "Download PDF" button: a real copy of the real compiled file. */
export async function copyFileTo(sourcePath: string, destinationPath: string): Promise<void> {
  await copyFile(sourcePath, destinationPath);
}
