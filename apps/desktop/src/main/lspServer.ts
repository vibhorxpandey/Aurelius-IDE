/**
 * Spawns `aurelius-lsp` and relays JSON-RPC over stdio to the renderer via IPC.
 *
 * Monaco has no built-in LSP client, and `monaco-languageclient` wants a WebSocket
 * transport that would mean running a local server just to talk to a process we already
 * spawned. Instead: this process owns the child's stdio, does the `Content-Length` framing
 * itself, and forwards whole JSON-RPC messages to the renderer as IPC events. The renderer
 * sends messages back the same way. Electron's IPC is the transport; the LSP framing exists
 * only on this side of it.
 */
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { app, type BrowserWindow } from "electron";
import type { JsonRpcMessage, ServerStatus } from "../shared/lsp-types";

/**
 * A packaged build ships its own interpreter — see `scripts/bundle-python.mjs` — so a
 * user with no Python installed at all can still run the app. It goes first: a stray
 * system Python missing `aurelius_ide` would otherwise "succeed" at spawning and then
 * fail the module import, wasting the one attempt a bundled interpreter would have won.
 */
function bundledPython(): string | null {
  if (!app.isPackaged) return null;
  const candidate = join(process.resourcesPath, "python-embed", "python.exe");
  return existsSync(candidate) ? candidate : null;
}

function candidatePythons(): string[] {
  const bundled = bundledPython();
  const systemCandidates = ["python", "python3", "py"];
  return bundled ? [bundled, ...systemCandidates] : systemCandidates;
}

export class LspServerProcess {
  private child: ChildProcessWithoutNullStreams | null = null;
  private buffer = Buffer.alloc(0);
  private window: BrowserWindow;

  constructor(window: BrowserWindow) {
    this.window = window;
  }

  async start(): Promise<void> {
    this.report({ state: "starting", detail: "Locating a Python interpreter…" });

    for (const python of candidatePythons()) {
      const ok = await this.tryPython(python);
      if (ok) return;
    }

    this.report({
      state: "not-found",
      detail:
        "No Python interpreter with aurelius_ide was found. Install with: " +
        'pip install -e ".[lsp]" from the aurelius-ide repository root.',
    });
  }

  private tryPython(python: string): Promise<boolean> {
    return new Promise((resolvePromise) => {
      // Run as a module rather than relying on the aurelius-lsp console script being on
      // PATH — the same PATH problem the roadmap flags for TeX applies to any bundled
      // interpreter, so -m is the form that survives a bundled runtime later.
      const child = spawn(python, ["-m", "aurelius_ide.lsp"], {
        stdio: ["pipe", "pipe", "pipe"],
      });

      let settled = false;
      const fail = () => {
        if (!settled) {
          settled = true;
          resolvePromise(false);
        }
      };

      child.once("error", fail);

      child.stderr.on("data", (chunk: Buffer) => {
        // pygls logs startup info to stderr; only the first bytes tell us whether the
        // module import itself failed (wrong interpreter) versus the server just being
        // chatty (real server, keep it).
        const text = chunk.toString("utf-8");
        if (!settled && /ModuleNotFoundError|ImportError|Traceback/.test(text)) {
          settled = true;
          child.kill();
          resolvePromise(false);
        }
      });

      child.stdout.once("data", (chunk: Buffer) => {
        if (settled) return;
        settled = true;
        this.child = child;
        this.buffer = Buffer.alloc(0);
        this.report({ state: "running", detail: `Started via ${python} -m aurelius_ide.lsp` });
        this.attach(child);
        // Replay the first chunk through the framer — it may already contain a full message.
        this.onData(chunk);
        resolvePromise(true);
      });

      // A server that never prints anything (silent success) still counts as found: give
      // it a moment, then attach anyway rather than declaring failure.
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

  private attach(child: ChildProcessWithoutNullStreams): void {
    child.stdout.on("data", (chunk: Buffer) => this.onData(chunk));
    child.stderr.on("data", (chunk: Buffer) => {
      // Surfaced in the renderer's Output-channel-equivalent rather than swallowed, so a
      // real server error is visible instead of the panel just silently not updating.
      this.window.webContents.send("lsp:stderr", chunk.toString("utf-8"));
    });
    child.on("exit", (code) => {
      this.child = null;
      this.report({ state: "crashed", detail: `Server exited with code ${code}` });
    });
  }

  private onData(chunk: Buffer): void {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const headerEnd = this.buffer.indexOf("\r\n\r\n");
      if (headerEnd === -1) return;
      const header = this.buffer.subarray(0, headerEnd).toString("ascii");
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match) {
        // Not a framed LSP message (e.g. a stray print). Drop the bad header and resync.
        this.buffer = this.buffer.subarray(headerEnd + 4);
        continue;
      }
      const length = Number(match[1]);
      const bodyStart = headerEnd + 4;
      if (this.buffer.length < bodyStart + length) return; // wait for the rest

      const body = this.buffer.subarray(bodyStart, bodyStart + length).toString("utf-8");
      this.buffer = this.buffer.subarray(bodyStart + length);
      try {
        const message = JSON.parse(body) as JsonRpcMessage;
        this.window.webContents.send("lsp:message", message);
      } catch {
        // A malformed frame must not take down the relay for every message after it.
      }
    }
  }

  send(message: JsonRpcMessage): void {
    if (!this.child || !this.child.stdin.writable) return;
    const body = Buffer.from(JSON.stringify(message), "utf-8");
    const header = Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, "ascii");
    this.child.stdin.write(Buffer.concat([header, body]));
  }

  private report(status: ServerStatus): void {
    this.window.webContents.send("lsp:status", status);
  }

  stop(): void {
    this.child?.kill();
    this.child = null;
  }
}
