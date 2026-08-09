"use strict";
const electron = require("electron");
const api = {
  workspace: {
    defaultPath: () => electron.ipcRenderer.invoke("workspace:default-path"),
    list: (path) => electron.ipcRenderer.invoke("workspace:list", path),
    read: (path) => electron.ipcRenderer.invoke("workspace:read", path),
    write: (path, content) => electron.ipcRenderer.invoke("workspace:write", path, content),
    isDirectory: (path) => electron.ipcRenderer.invoke("workspace:is-directory", path),
    openFolderDialog: () => electron.ipcRenderer.invoke("workspace:open-folder-dialog")
  },
  lsp: {
    send: (message) => electron.ipcRenderer.send("lsp:send", message),
    restart: () => electron.ipcRenderer.invoke("lsp:restart"),
    onMessage: (handler) => {
      const listener = (_e, message) => handler(message);
      electron.ipcRenderer.on("lsp:message", listener);
      return () => electron.ipcRenderer.removeListener("lsp:message", listener);
    },
    onStatus: (handler) => {
      const listener = (_e, status) => handler(status);
      electron.ipcRenderer.on("lsp:status", listener);
      return () => electron.ipcRenderer.removeListener("lsp:status", listener);
    },
    onStderr: (handler) => {
      const listener = (_e, text) => handler(text);
      electron.ipcRenderer.on("lsp:stderr", listener);
      return () => electron.ipcRenderer.removeListener("lsp:stderr", listener);
    }
  }
};
electron.contextBridge.exposeInMainWorld("aurelius", api);
