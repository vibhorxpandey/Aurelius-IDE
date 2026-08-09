import { join } from "node:path";
import { app, BrowserWindow, ipcMain, dialog, shell } from "electron";
import { LspServerProcess } from "./lspServer.js";
import { listDirectory, readTextFile, writeTextFile, isDirectory } from "./workspaceFs.js";
import type { JsonRpcMessage } from "../shared/lsp-types";

let mainWindow: BrowserWindow | null = null;
let lsp: LspServerProcess | null = null;

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
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => lsp?.stop());

function registerIpc(): void {
  ipcMain.handle("workspace:default-path", () => DEFAULT_WORKSPACE);
  ipcMain.handle("workspace:list", (_e, path: string) => listDirectory(path));
  ipcMain.handle("workspace:read", (_e, path: string) => readTextFile(path));
  ipcMain.handle("workspace:write", (_e, path: string, content: string) =>
    writeTextFile(path, content)
  );
  ipcMain.handle("workspace:is-directory", (_e, path: string) => isDirectory(path));

  ipcMain.handle("workspace:open-folder-dialog", async () => {
    if (!mainWindow) return null;
    const result = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });

  ipcMain.on("lsp:send", (_e, message: JsonRpcMessage) => lsp?.send(message));
  ipcMain.handle("lsp:restart", async () => {
    lsp?.stop();
    if (mainWindow) {
      lsp = new LspServerProcess(mainWindow);
      await lsp.start();
    }
  });
}
