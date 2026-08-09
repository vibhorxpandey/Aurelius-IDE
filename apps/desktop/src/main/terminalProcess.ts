/**
 * A real shell process, streamed to the renderer — not a mock terminal that echoes typed
 * text back at you. Deliberately not a full PTY: `node-pty` needs native compilation
 * (node-gyp, a C++ toolchain) which is a real risk to pull into a prototype's dependency
 * tree without a controlled build environment to test it in. `child_process.spawn` with
 * piped stdio is the honest middle ground — actual commands actually run and actual
 * output actually streams back, but full-screen TUI programs (vim, htop) and readline's
 * fancy line-editing won't work, because there's no real TTY underneath. That trade-off is
 * stated here and in the terminal panel itself, not hidden.
 */
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { BrowserWindow } from "electron";

function defaultShell(): { command: string; args: string[] } {
  if (process.platform === "win32") {
    return { command: process.env["COMSPEC"] || "cmd.exe", args: [] };
  }
  return { command: process.env["SHELL"] || "/bin/bash", args: ["-i"] };
}

export class TerminalProcess {
  private child: ChildProcessWithoutNullStreams | null = null;

  constructor(private readonly window: BrowserWindow) {}

  start(cwd: string): void {
    if (this.child) return;
    const { command, args } = defaultShell();

    try {
      const child = spawn(command, args, {
        cwd,
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, TERM: "xterm-256color" },
      });
      this.child = child;

      child.stdout.on("data", (chunk: Buffer) => {
        this.window.webContents.send("terminal:data", chunk.toString("utf-8"));
      });
      child.stderr.on("data", (chunk: Buffer) => {
        this.window.webContents.send("terminal:data", chunk.toString("utf-8"));
      });
      child.on("exit", (code) => {
        this.window.webContents.send("terminal:exit", code);
        this.child = null;
      });
      child.on("error", (err) => {
        this.window.webContents.send(
          "terminal:data",
          `\r\n[terminal] could not start ${command}: ${err.message}\r\n`
        );
      });
    } catch (err) {
      this.window.webContents.send(
        "terminal:data",
        `[terminal] could not start a shell: ${(err as Error).message}\r\n`
      );
    }
  }

  write(data: string): void {
    if (this.child?.stdin.writable) this.child.stdin.write(data);
  }

  stop(): void {
    this.child?.kill();
    this.child = null;
  }
}
