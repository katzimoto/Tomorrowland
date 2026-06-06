/* global React, Icon, Button, Badge, SearchInput, DOCUMENTS */

function mimeIconName(mime) {
  if (!mime) return "file";
  if (mime.includes("pdf")) return "file-text";
  if (mime.startsWith("image/")) return "image";
  if (mime.includes("zip") || mime.includes("archive")) return "archive";
  if (mime.includes("mail") || mime.includes("message")) return "mail";
  if (mime.includes("html") || mime.includes("text")) return "file-text";
  return "file";
}

function FilterPanel({ filters, onChange }) {
  function toggle(group, value) {
    const cur = filters[group] || [];
    const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    onChange({ ...filters, [group]: next });
  }
  function clear(group) { onChange({ ...filters, [group]: [] }); }

  const fileTypes = [
    ["application/pdf", "PDF"],
    ["text/html", "HTML"],
    ["application/vnd.openxmlformats", "Office"],
    ["message/rfc822", "Email"],
    ["application/zip", "Archive"],
    ["image/", "Image"],
  ];
  const sources = ["Confluence", "Jira", "Legal Docs", "Engineering Wiki"];
  const translations = [["fast", "Fast translation"], ["high", "High quality"]];

  return (
    <aside className="filter-panel" aria-label="Search filters">
      <div className="fp-section">
        <div className="fp-header">
          <span className="fp-label">File type</span>
          {(filters.file_type?.length ?? 0) > 0 && (
            <button className="fp-clear" onClick={() => clear("file_type")}>Clear</button>
          )}
        </div>
        <div className="fp-options">
          {fileTypes.map(([value, label]) => (
            <label key={value} className="fp-option">
              <input
                type="checkbox"
                checked={!!filters.file_type?.includes(value)}
                onChange={() => toggle("file_type", value)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div className="fp-section">
        <div className="fp-header">
          <span className="fp-label">Source</span>
          {(filters.source?.length ?? 0) > 0 && (
            <button className="fp-clear" onClick={() => clear("source")}>Clear</button>
          )}
        </div>
        <div className="fp-options">
          {sources.map((s) => (
            <label key={s} className="fp-option">
              <input
                type="checkbox"
                checked={!!filters.source?.includes(s)}
                onChange={() => toggle("source", s)}
              />
              {s}
            </label>
          ))}
        </div>
      </div>

      <div className="fp-section">
        <div className="fp-header">
          <span className="fp-label">Translation</span>
        </div>
        <div className="fp-options">
          {translations.map(([value, label]) => (
            <label key={value} className="fp-option">
              <input
                type="checkbox"
                checked={!!filters.translation_quality?.includes(value)}
                onChange={() => toggle("translation_quality", value)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div className="fp-section">
        <div className="fp-header">
          <span className="fp-label">Date range</span>
        </div>
        <div className="fp-options">
          <select className="text-input" style={{ height: 32 }} defaultValue="any">
            <option value="any">Any time</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="1y">Last year</option>
          </select>
        </div>
      </div>
    </aside>
  );
}

function ResultRow({ result, selected, onSelect, onClick, onPreview }) {
  const visibleTags = result.tags.slice(0, 3);
  return (
    <div
      className={`result-row${selected ? " selected" : ""}`}
      onMouseEnter={onSelect}
      onClick={onClick}
      role="option"
      aria-selected={selected}
    >
      <div className="rr-left">
        <span className="rr-mime"><Icon name={mimeIconName(result.mime)} size={18} /></span>
      </div>
      <div className="rr-main">
        <span className="rr-title">{result.title}</span>
        <span
          className="rr-snippet"
          dangerouslySetInnerHTML={{ __html: result.snippet }}
        />
        <div className="rr-meta">
          <span className="rr-source">{result.source}</span>
          {visibleTags.map((t) => (
            <React.Fragment key={t}>
              <span className="rr-dot">·</span>
              <span className="rr-tag">{t}</span>
            </React.Fragment>
          ))}
          {result.translation && (
            <>
              <span className="rr-dot">·</span>
              <span className="rr-trans">
                {result.translation === "fast" ? "Fast translation" : "High quality"}
              </span>
            </>
          )}
        </div>
      </div>
      <div className="rr-right">
        <span className="rr-date">{result.updatedLabel}</span>
        <button
          className="rr-preview"
          onClick={(e) => { e.stopPropagation(); onPreview?.(); }}
        >
          <Icon name="eye" size={12} /> Preview
        </button>
      </div>
    </div>
  );
}

function SearchView({ onOpenDocument }) {
  const [query, setQuery] = React.useState("incident response");
  const [mode, setMode] = React.useState("hybrid");
  const [filters, setFilters] = React.useState({});
  const [selectedIndex, setSelectedIndex] = React.useState(0);
  const [previewDoc, setPreviewDoc] = React.useState(null);

  const results = React.useMemo(() => {
    let r = DOCUMENTS;
    const q = query.trim().toLowerCase();
    if (q) {
      r = r.filter((d) =>
        (d.title + " " + d.tags.join(" ") + " " + d.snippet).toLowerCase().includes(q),
      );
    }
    if (filters.source?.length) r = r.filter((d) => filters.source.includes(d.source));
    if (filters.translation_quality?.length) r = r.filter((d) => filters.translation_quality.includes(d.translation));
    return r;
  }, [query, filters]);

  const total = results.length;

  // Active filter chips
  const chips = [];
  (filters.file_type || []).forEach((ft) => chips.push({ label: ft.split("/").pop(), remove: () => setFilters((f) => ({ ...f, file_type: f.file_type.filter((v) => v !== ft) })) }));
  (filters.source || []).forEach((s) => chips.push({ label: s, remove: () => setFilters((f) => ({ ...f, source: f.source.filter((v) => v !== s) })) }));
  (filters.translation_quality || []).forEach((tq) => chips.push({ label: tq === "fast" ? "Fast translation" : "High quality", remove: () => setFilters((f) => ({ ...f, translation_quality: f.translation_quality.filter((v) => v !== tq) })) }));

  return (
    <div className="search-page" data-screen-label="Search">
      <header className="search-header">
        <h1 className="search-title">Search</h1>
        <div className="search-row">
          <SearchInput value={query} onChange={setQuery} autoFocus />
          <Button>Search</Button>
        </div>
      </header>

      <div className="toolbar">
        <div className="mode-group" role="group" aria-label="Search mode">
          {["hybrid", "keyword", "semantic"].map((m) => (
            <button
              key={m}
              className={`mode-btn${mode === m ? " active" : ""}`}
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
            >
              {m[0].toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>
        <span className="result-count">{total.toLocaleString()} result{total !== 1 ? "s" : ""}</span>
      </div>

      {chips.length > 0 && (
        <div className="active-filters">
          {chips.map((c, i) => (
            <span key={i} className="filter-chip">
              {c.label}
              <button className="filter-chip-remove" onClick={c.remove} aria-label={`Remove filter ${c.label}`}>
                <Icon name="x" size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="search-body">
        <FilterPanel filters={filters} onChange={(f) => { setFilters(f); setSelectedIndex(0); }} />

        <div className="results">
          <p className="kb-help">
            Use ↑/↓ or j/k to choose a result, Enter to open, Space to preview, and Esc to close preview.
          </p>
          <div className="results-list" role="listbox" aria-label="Search results">
            {results.length === 0 ? (
              <div className="empty">
                <h2>No results found</h2>
                <p>No accessible documents match your query. Try different terms or remove filters.</p>
              </div>
            ) : (
              results.map((r, i) => (
                <ResultRow
                  key={r.id}
                  result={r}
                  selected={i === selectedIndex}
                  onSelect={() => setSelectedIndex(i)}
                  onClick={() => onOpenDocument?.(r.id)}
                  onPreview={() => setPreviewDoc(r)}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {previewDoc && (
        <div className="dialog-backdrop" onClick={() => setPreviewDoc(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <span className="dialog-title">{previewDoc.title}</span>
              <button className="dialog-close" onClick={() => setPreviewDoc(null)}>
                <Icon name="x" size={16} />
              </button>
            </div>
            <div className="dialog-body">
              <p className="meta" style={{ marginBottom: 16 }}>
                {previewDoc.source} · {previewDoc.mime}
              </p>
              <p dangerouslySetInnerHTML={{ __html: previewDoc.snippet.replace(/<\/?mark>/g, "") }} />
              <p className="meta" style={{ marginTop: 16 }}>
                {previewDoc.tags.join(", ")}
              </p>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 24 }}>
                <Button variant="secondary" onClick={() => setPreviewDoc(null)}>Close preview</Button>
                <Button onClick={() => { setPreviewDoc(null); onOpenDocument?.(previewDoc.id); }}>Open document</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

window.SearchView = SearchView;
