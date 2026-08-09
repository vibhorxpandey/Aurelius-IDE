"use strict";
const node_path = require("node:path");
const electron = require("electron");
const node_child_process = require("node:child_process");
const promises = require("node:fs/promises");
const CANDIDATE_PYTHONS = ["python", "python3", "py"];
class LspServerProcess {
  child = null;
  buffer = Buffer.alloc(0);
  window;
  constructor(window) {
    this.window = window;
  }
  async start() {
    this.report({ state: "starting", detail: "Locating a Python interpreter…" });
    for (const python of CANDIDATE_PYTHONS) {
      const ok = await this.tryPython(python);
      if (ok) return;
    }
    this.report({
      state: "not-found",
      detail: 'No Python interpreter with aurelius_ide was found. Install with: pip install -e ".[lsp]" from the aurelius-ide repository root.'
    });
  }
  tryPython(python) {
    return new Promise((resolvePromise) => {
      const child = node_child_process.spawn(python, ["-m", "aurelius_ide.lsp"], {
        stdio: ["pipe", "pipe", "pipe"]
      });
      let settled = false;
      const fail = () => {
        if (!settled) {
          settled = true;
          resolvePromise(false);
        }
      };
      child.once("error", fail);
      child.stderr.on("data", (chunk) => {
        const text = chunk.toString("utf-8");
        if (!settled && /ModuleNotFoundError|ImportError|Traceback/.test(text)) {
          settled = true;
          child.kill();
          resolvePromise(false);
        }
      });
      child.stdout.once("data", (chunk) => {
        if (settled) return;
        settled = true;
        this.child = child;
        this.buffer = Buffer.alloc(0);
        this.report({ state: "running", detail: `Started via ${python} -m aurelius_ide.lsp` });
        this.attach(child);
        this.onData(chunk);
        resolvePromise(true);
      });
      setTimeout(() => {
        if (settled) return;
        settled = true;
        this.child = child;
        this.report({ state: "running", detail: `Started via ${python} -m aurelius_ide.lsp` });
        this.attach(child);
        resolvePromise(true);
      }, 900);
    });
  }
  attach(child) {
    child.stdout.on("data", (chunk) => this.onData(chunk));
    child.stderr.on("data", (chunk) => {
      this.window.webContents.send("lsp:stderr", chunk.toString("utf-8"));
    });
    child.on("exit", (code) => {
      this.child = null;
      this.report({ state: "crashed", detail: `Server exited with code ${code}` });
    });
  }
  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      const headerEnd = this.buffer.indexOf("\r\n\r\n");
      if (headerEnd === -1) return;
      const header = this.buffer.subarray(0, headerEnd).toString("ascii");
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match) {
        this.buffer = this.buffer.subarray(headerEnd + 4);
        continue;
      }
      const length = Number(match[1]);
      const bodyStart = headerEnd + 4;
      if (this.buffer.length < bodyStart + length) return;
      const body = this.buffer.subarray(bodyStart, bodyStart + length).toString("utf-8");
      this.buffer = this.buffer.subarray(bodyStart + length);
      try {
        const message = JSON.parse(body);
        this.window.webContents.send("lsp:message", message);
      } catch {
      }
    }
  }
  send(message) {
    if (!this.child || !this.child.stdin.writable) return;
    const body = Buffer.from(JSON.stringify(message), "utf-8");
    const header = Buffer.from(`Content-Length: ${body.length}\r
\r
`, "ascii");
    this.child.stdin.write(Buffer.concat([header, body]));
  }
  report(status) {
    this.window.webContents.send("lsp:status", status);
  }
  stop() {
    this.child?.kill();
    this.child = null;
  }
}
async function listDirectory(path) {
  const entries = await promises.readdir(path, { withFileTypes: true });
  return entries.filter((e) => !e.name.startsWith(".") && e.name !== "__pycache__").map((e) => ({
    name: e.name,
    path: node_path.join(path, e.name),
    isDirectory: e.isDirectory()
  })).sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}
async function readTextFile(path) {
  return promises.readFile(path, "utf-8");
}
async function writeTextFile(path, content) {
  await promises.writeFile(path, content, "utf-8");
}
async function isDirectory(path) {
  const s = await promises.stat(path);
  return s.isDirectory();
}
let mainWindow = null;
let lsp = null;
const DEFAULT_WORKSPACE = node_path.join(__dirname, "../../demo-workspace");
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 860,
    minHeight: 560,
    show: false,
    backgroundColor: "#1e1e1e",
    autoHideMenuBar: true,
    title: "Aurelius",
    webPreferences: {
      preload: node_path.join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true
    }
  });
  mainWindow.on("ready-to-show", () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler((details) => {
    void electron.shell.openExternal(details.url);
    return { action: "deny" };
  });
  const devServerUrl = process.env["ELECTRON_RENDERER_URL"];
  if (devServerUrl) {
    void mainWindow.loadURL(devServerUrl);
  } else {
    void mainWindow.loadFile(node_path.join(__dirname, "../renderer/index.html"));
  }
  lsp = new LspServerProcess(mainWindow);
  void lsp.start();
}
electron.app.whenReady().then(() => {
  registerIpc();
  createWindow();
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("window-all-closed", () => {
  lsp?.stop();
  if (process.platform !== "darwin") electron.app.quit();
});
electron.app.on("before-quit", () => lsp?.stop());
function registerIpc() {
  electron.ipcMain.handle("workspace:default-path", () => DEFAULT_WORKSPACE);
  electron.ipcMain.handle("workspace:list", (_e, path) => listDirectory(path));
  electron.ipcMain.handle("workspace:read", (_e, path) => readTextFile(path));
  electron.ipcMain.handle(
    "workspace:write",
    (_e, path, content) => writeTextFile(path, content)
  );
  electron.ipcMain.handle("workspace:is-directory", (_e, path) => isDirectory(path));
  electron.ipcMain.handle("workspace:open-folder-dialog", async () => {
    if (!mainWindow) return null;
    const result = await electron.dialog.showOpenDialog(mainWindow, { properties: ["openDirectory"] });
    return result.canceled ? null : result.filePaths[0] ?? null;
  });
  electron.ipcMain.on("lsp:send", (_e, message) => lsp?.send(message));
  electron.ipcMain.handle("lsp:restart", async () => {
    lsp?.stop();
    if (mainWindow) {
      lsp = new LspServerProcess(mainWindow);
      await lsp.start();
    }
  });
}
