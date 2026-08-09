import { contextBridge, ipcRenderer } from "electron";
import type { AureliusApi, FsEntry, JsonRpcMessage, ServerStatus } from "../shared/lsp-types";

/**
 * The only surface the renderer can reach into the OS through. `contextIsolation` is on, so
 * this is genuinely the whole API — there is no way for renderer code to touch `fs` or
 * `child_process` directly, matching the security model the real desktop shell will need
 * for Stage 13's hardened-runtime entitlements even though this prototype doesn't sign
 * anything yet.
 *
 * Typed against `AureliusApi` from `shared/` — if this drifts from that contract, it fails
 * to compile here rather than surfacing as `undefined` deep in a renderer component.
 */
const api: AureliusApi = {
  workspace: {
    defaultPath: (): Promise<string> => ipcRenderer.invoke("workspace:default-path"),
    list: (path: string): Promise<FsEntry[]> => ipcRenderer.invoke("workspace:list", path),
    read: (path: string): Promise<string> => ipcRenderer.invoke("workspace:read", path),
    write: (path: string, content: string): Promise<void> =>
      ipcRenderer.invoke("workspace:write", path, content),
    isDirectory: (path: string): Promise<boolean> =>
      ipcRenderer.invoke("workspace:is-directory", path),
    openFolderDialog: (): Promise<string | null> =>
      ipcRenderer.invoke("workspace:open-folder-dialog"),
  },
  lsp: {
    send: (message: JsonRpcMessage): void => ipcRenderer.send("lsp:send", message),
    restart: (): Promise<void> => ipcRenderer.invoke("lsp:restart"),
    onMessage: (handler: (message: JsonRpcMessage) => void): (() => void) => {
      const listener = (_e: Electron.IpcRendererEvent, message: JsonRpcMessage) =>
        handler(message);
      ipcRenderer.on("lsp:message", listener);
      return () => ipcRenderer.removeListener("lsp:message", listener);
    },
    onStatus: (handler: (status: ServerStatus) => void): (() => void) => {
      const listener = (_e: Electron.IpcRendererEvent, status: ServerStatus) => handler(status);
      ipcRenderer.on("lsp:status", listener);
      return () => ipcRenderer.removeListener("lsp:status", listener);
    },
    onStderr: (handler: (text: string) => void): (() => void) => {
      const listener = (_e: Electron.IpcRendererEvent, text: string) => handler(text);
      ipcRenderer.on("lsp:stderr", listener);
      return () => ipcRenderer.removeListener("lsp:stderr", listener);
    },
  },
  terminal: {
    start: (): void => ipcRenderer.send("terminal:start"),
    write: (data: string): void => ipcRenderer.send("terminal:write", data),
    onData: (handler: (chunk: string) => void): (() => void) => {
      const listener = (_e: Electron.IpcRendererEvent, chunk: string) => handler(chunk);
      ipcRenderer.on("terminal:data", listener);
      return () => ipcRenderer.removeListener("terminal:data", listener);
    },
    onExit: (handler: (code: number | null) => void): (() => void) => {
      const listener = (_e: Electron.IpcRendererEvent, code: number | null) => handler(code);
      ipcRenderer.on("terminal:exit", listener);
      return () => ipcRenderer.removeListener("terminal:exit", listener);
    },
  },
};

contextBridge.exposeInMainWorld("aurelius", api);
