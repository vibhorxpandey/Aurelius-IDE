import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";
import { getApi, isElectron } from "../platform";
import { DownloadIcon, RefreshIcon } from "./icons";

// Pinned to 4.10.38, not the latest 6.x: newer pdfjs-dist releases call brand-new
// TypedArray/Map built-ins (`Uint8Array.prototype.toHex`, `Map.prototype.getOrInsertComputed`)
// with no feature-detection, and Electron 33's bundled Chromium 130 predates all of them —
// every compiled PDF failed to render. 4.10.38 targets the browser generation this Electron
// actually ships.
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface PdfPreviewProps {
  pdfPath: string;
  /** Bumped by the caller after a fresh compile, so the preview reloads the new bytes. */
  refreshToken: number;
}

/**
 * Renders the actually-compiled PDF — real bytes read off disk via IPC, decoded and
 * rasterised by pdf.js, not a mock. White page canvases on a neutral background, the way
 * every PDF viewer renders paper: the page is white, the surroundings are not.
 */
export default function PdfPreview({ pdfPath, refreshToken }: PdfPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string>("");
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");

    async function render() {
      try {
        const base64 = await getApi().workspace.readBinary(pdfPath);
        if (cancelled) return;
        const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));

        const doc = await pdfjsLib.getDocument({ data: bytes }).promise;
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = "";

        for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
          const page = await doc.getPage(pageNum);
          const viewport = page.getViewport({ scale: 1.4 });
          const canvas = document.createElement("canvas");
          canvas.className = "pdf-preview__page";
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          const context = canvas.getContext("2d");
          if (!context) continue;
          await page.render({ canvasContext: context, viewport }).promise;
          if (cancelled) return;
          containerRef.current.appendChild(canvas);
        }
        if (!cancelled) setStatus("ready");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setStatus("error");
        }
      }
    }

    void render();
    return () => {
      cancelled = true;
    };
  }, [pdfPath, refreshToken]);

  const download = async () => {
    setDownloading(true);
    try {
      const saved = await getApi().workspace.downloadFile(pdfPath);
      if (saved) {
        setDownloaded(true);
        setTimeout(() => setDownloaded(false), 1800);
      }
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="pdf-preview">
      <div className="pdf-preview__toolbar">
        <span className="pdf-preview__filename">{pdfPath.split(/[\\/]/).pop()}</span>
        <button className="pdf-preview__download" onClick={() => void download()} disabled={downloading || !isElectron}>
          <DownloadIcon size={13} />
          <span>{downloaded ? "Saved" : downloading ? "Saving…" : "Download PDF"}</span>
        </button>
      </div>
      <div className="pdf-preview__scroll">
        {status === "loading" && (
          <div className="pdf-preview__status">
            <RefreshIcon size={16} />
            <span>Rendering compiled PDF…</span>
          </div>
        )}
        {status === "error" && (
          <div className="pdf-preview__status pdf-preview__status--error">{error}</div>
        )}
        <div ref={containerRef} className="pdf-preview__pages" />
      </div>
    </div>
  );
}
