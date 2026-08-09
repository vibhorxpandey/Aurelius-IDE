import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { getApi } from "../platform";

/**
 * A real shell process (see `main/terminalProcess.ts`), not a full PTY — there's no
 * `node-pty` underneath, so this implements line editing itself: it echoes typed
 * characters locally and sends a complete line to the process on Enter. That means
 * arrow-key history and full-screen programs (vim, htop) don't work; ordinary commands
 * with streaming output do, because the process really is running and its real stdout is
 * really what's arriving.
 */
export default function TerminalPanel({ visible }: { visible: boolean }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const lineRef = useRef("");
  const startedRef = useRef(false);

  useEffect(() => {
    if (!hostRef.current) return;
    const term = new XTerm({
      theme: {
        background: "#181818",
        foreground: "#cccccc",
        cursor: "#cccccc",
      },
      fontFamily: "var(--font-mono)",
      fontSize: 13,
      cursorBlink: true,
      convertEol: true,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(hostRef.current);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;

    term.writeln("Aurelius terminal — a real shell process, line-buffered (no full PTY).");
    term.write("$ ");

    const api = getApi();
    const offData = api.terminal.onData((chunk) => term.write(chunk));
    const offExit = api.terminal.onExit((code) => {
      term.writeln(`\r\n[process exited with code ${code}]`);
    });

    if (!startedRef.current) {
      startedRef.current = true;
      api.terminal.start();
    }

    const dataDisposable = term.onData((data) => {
      if (data === "\r") {
        term.write("\r\n");
        api.terminal.write(lineRef.current + "\n");
        lineRef.current = "";
      } else if (data === "\x7f") {
        // Backspace — xterm sends DEL (0x7F), not the Backspace keycode.
        if (lineRef.current.length > 0) {
          lineRef.current = lineRef.current.slice(0, -1);
          term.write("\b \b");
        }
      } else if (data.charCodeAt(0) >= 32) {
        lineRef.current += data;
        term.write(data);
      }
      // Control sequences (arrows, Ctrl+C, …) are intentionally ignored — there's no PTY
      // underneath to give them meaning, and half-implementing signal delivery over a
      // plain pipe would be worse than clearly not supporting it.
    });

    return () => {
      dataDisposable.dispose();
      offData();
      offExit();
      term.dispose();
    };
  }, []);

  useEffect(() => {
    if (visible) {
      requestAnimationFrame(() => {
        fitRef.current?.fit();
        termRef.current?.focus();
      });
    }
  }, [visible]);

  useEffect(() => {
    const onResize = () => fitRef.current?.fit();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return <div ref={hostRef} className="terminal-host" style={{ display: visible ? "block" : "none" }} />;
}
