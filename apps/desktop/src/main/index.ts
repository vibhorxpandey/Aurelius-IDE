import { join, basename } from "node:path";
import { app, BrowserWindow, ipcMain, dialog, shell } from "electron";
import { LspServerProcess } from "./lspServer.js";
import { TerminalProcess } from "./terminalProcess.js";
import {
  listDirectory,
  readTextFile,
  writeTextFile,
  isDirectory,
  readBinaryFileBase64,
  createFile,
  createFolder,
  copyFileTo,
} from "./workspaceFs.js";
import type { JsonRpcMessage } from "../shared/lsp-types";

let mainWindow: BrowserWindow | null = null;
let lsp: LspServerProcess | null = null;
let terminal: TerminalProcess | null = null;

// The bundled demo workspace ships intentional errors — an undefined key, uncited claims,
// an orphaned bibliography entry — so the moment the window opens, the Problems panel has
// real content instead of an empty state that proves nothing.
const DEFAULT_WORKSPACE = join(__dirname, "../../demo-workspace");

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 860,
    minHeight: 560,
    show: false,
    backgroundColor: "#1e1e1e",
    autoHideMenuBar: true,
    title: "Aurelius",
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true,
    },
  });

  mainWindow.on("ready-to-show", () => mainWindow?.show());

  mainWindow.webContents.setWindowOpenHandler((details) => {
    void shell.openExternal(details.url);
    return { action: "deny" };
  });

  const devServerUrl = process.env["ELECTRON_RENDERER_URL"];
  if (devServerUrl) {
    void mainWindow.loadURL(devServerUrl);
  } else {
    void mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }

  lsp = new LspServerProcess(mainWindow);
  void lsp.start();

  terminal = new TerminalProcess(mainWindow);
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  lsp?.stop();
  terminal?.stop();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  lsp?.stop();
  terminal?.stop();
});

function registerIpc(): void {
  ipcMain.handle("workspace:default-path", () => DEFAULT_WORKSPACE);
  ipcMain.handle("workspace:list", (_e, path: string) => listDirectory(path));
  ipcMain.handle("workspace:read", (_e, path: string) => readTextFile(path));
  ipcMain.handle("workspace:write", (_e, path: string, content: string) =>
    writeTextFile(path, content)
  );
  ipcMain.handle("workspace:is-directory", (_e, path: string) => isDirectory(path));
  ipcMain.handle("workspace:read-binary", (_e, path: string) => readBinaryFileBase64(path));
  ipcMain.handle("workspace:create-file", (_e, path: string) => createFile(path));
  ipcMain.handle("workspace:create-folder", (_e, path: string) => createFolder(path));

  ipcMain.handle("workspace:open-folder-dialog", async () => {
    if (!mainWindow) return null;
    const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });

  // Backs "Download PDF": a real save dialog, then a real file copy of the real compiled
  // artefact — never a synthesised placeholder.
  ipcMain.handle("workspace:download-file", async (_e, sourcePath: string) => {
    if (!mainWindow) return false;
    const result = await dialog.showSaveDialog(mainWindow, {
      defaultPath: basename(sourcePath),
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (result.canceled || !result.filePath) return false;
    await copyFileTo(sourcePath, result.filePath);
    return true;
  });

  ipcMain.on("lsp:send", (_e, message: JsonRpcMessage) => lsp?.send(message));
  ipcMain.handle("lsp:restart", async () => {
    lsp?.stop();
    if (mainWindow) {
      lsp = new LspServerProcess(mainWindow);
      await lsp.start();
    }
  });

  ipcMain.on("terminal:start", () => terminal?.start(DEFAULT_WORKSPACE));
  ipcMain.on("terminal:write", (_e, data: string) => terminal?.write(data));
}
