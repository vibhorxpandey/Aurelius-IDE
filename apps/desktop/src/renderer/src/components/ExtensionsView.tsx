import { useMemo, useState } from "react";
import { ALL_EXTENSIONS, CATEGORIES, type ExtensionCategory, type ExtensionEntry } from "../data/extensions";

/**
 * A marketplace-shaped catalogue, not a marketplace. Nothing here downloads or executes
 * code — "Install" just toggles local UI state. The four `builtin` entries (Bibliography,
 * Submission Gate, Diagrams, Agent Activity) are the real tools in this app; everything
 * else exists to show what a populated extensions view looks like for a research IDE, the
 * same way a floor-plan show home doesn't wire its outlets to anything.
 */
export default function ExtensionsView() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<ExtensionCategory | "all" | "installed">("all");
  const [installed, setInstalled] = useState<Set<string>>(
    () => new Set(ALL_EXTENSIONS.filter((e) => e.builtin).map((e) => e.id))
  );

  const toggleInstall = (id: string) => {
    setInstalled((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    return ALL_EXTENSIONS.filter((ext) => {
      if (category === "installed" && !installed.has(ext.id)) return false;
      if (category !== "all" && category !== "installed" && ext.category !== category) return false;
      if (!q) return true;
      return (
        ext.name.toLowerCase().includes(q) ||
        ext.publisher.toLowerCase().includes(q) ||
        ext.description.toLowerCase().includes(q) ||
        ext.category.toLowerCase().includes(q)
      );
    }).sort((a, b) => (b.builtin ? 1 : 0) - (a.builtin ? 1 : 0) || 0);
  }, [query, category, installed]);

  return (
    <div className="extensions">
      <div className="extensions__search">
        <input
          className="extensions__search-input"
          placeholder={`Search ${ALL_EXTENSIONS.length} extensions in Marketplace`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="extensions__filters">
        <button
          className="extensions__filter-chip"
          data-active={category === "all"}
          onClick={() => setCategory("all")}
        >
          All
        </button>
        <button
          className="extensions__filter-chip"
          data-active={category === "installed"}
          onClick={() => setCategory("installed")}
        >
          Installed ({installed.size})
        </button>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            className="extensions__filter-chip"
            data-active={category === c}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="extensions__list">
        {results.length === 0 ? (
          <div className="sidebar__empty">No extensions match &ldquo;{query}&rdquo;.</div>
        ) : (
          results.map((ext) => (
            <ExtensionRow
              key={ext.id}
              ext={ext}
              installedFlag={installed.has(ext.id)}
              onToggle={() => toggleInstall(ext.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function ExtensionRow({
  ext,
  installedFlag,
  onToggle,
}: {
  ext: ExtensionEntry;
  installedFlag: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="ext-row">
      <div className="ext-row__icon" style={{ background: ext.colour }}>
        {ext.initials}
      </div>
      <div className="ext-row__body">
        <div className="ext-row__title">
          <span className="ext-row__name">{ext.name}</span>
          {ext.verified && <span title="Verified publisher">✓</span>}
        </div>
        <div className="ext-row__desc">{ext.description}</div>
        <div className="ext-row__meta">
          <span>{ext.publisher}</span>
          <span>★ {ext.rating.toFixed(1)}</span>
          <span>{ext.installs} installs</span>
          <span>v{ext.version}</span>
        </div>
      </div>
      <button
        className="ext-row__install"
        data-installed={installedFlag}
        disabled={ext.builtin}
        onClick={onToggle}
        title={ext.builtin ? "Built into Aurelius" : undefined}
      >
        {ext.builtin ? "Built-in" : installedFlag ? "Installed" : "Install"}
      </button>
    </div>
  );
}
