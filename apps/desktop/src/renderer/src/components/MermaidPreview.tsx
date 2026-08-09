import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

let initialised = false;
function ensureInitialised(): void {
  if (initialised) return;
  mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
  initialised = true;
}

let renderCounter = 0;

/**
 * Live Mermaid rendering for `.mmd` files — the architecture/flowchart/diagram support a
 * research paper's supplementary materials actually need. Re-renders on a debounce as the
 * source changes; a syntax error while mid-edit shows as a quiet inline message rather
 * than blanking the last good diagram, since "still typing" is the overwhelmingly common
 * reason a diagram source is momentarily invalid.
 */
export default function MermaidPreview({ content }: { content: string }) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const lastGoodSvg = useRef<string>("");

  useEffect(() => {
    ensureInitialised();
    const timer = setTimeout(async () => {
      const source = content.trim();
      if (!source) {
        setSvg("");
        setError(null);
        return;
      }
      try {
        const id = `mermaid-${++renderCounter}`;
        const result = await mermaid.render(id, source);
        lastGoodSvg.current = result.svg;
        setSvg(result.svg);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setSvg(lastGoodSvg.current);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [content]);

  return (
    <div className="mermaid-preview">
      {error && <div className="mermaid-preview__error">{error.split("\n")[0]}</div>}
      {svg ? (
        <div className="mermaid-preview__canvas" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        !error && <div className="sidebar__empty">Empty diagram.</div>
      )}
    </div>
  );
}
