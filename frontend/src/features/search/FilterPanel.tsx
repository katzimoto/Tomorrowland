import { useState } from "react";
import type { SearchFilters } from "@/api/search";
import { useT } from "@/i18n/index";
import styles from "./FilterPanel.module.css";

interface FilterPanelProps {
  filters: SearchFilters;
  onChange: (f: SearchFilters) => void;
}

export function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const t = useT();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const FILE_TYPES = [
    { value: "application/pdf", label: t.filters.typePdf },
    { value: "application/msword", label: t.filters.typeOffice },
    { value: "message/rfc822", label: t.filters.typeEmail },
    { value: "application/zip", label: t.filters.typeArchive },
    { value: "text/plain", label: t.filters.typeText },
    { value: "image/", label: t.filters.typeImage },
  ];

  const TRANSLATION_OPTS = [
    { value: "fast", label: t.filters.transFast },
    { value: "high", label: t.filters.transHigh },
  ];

  const SORT_OPTS: { value: SearchFilters["sort_by"]; label: string }[] = [
    { value: "relevance", label: "Relevance" },
    { value: "updated_at", label: "Updated" },
    { value: "created_at", label: "Created" },
  ];

  const hasAny =
    (filters.file_type?.length ?? 0) > 0 ||
    (filters.translation_quality?.length ?? 0) > 0 ||
    !!filters.date_from ||
    !!filters.include_older_versions ||
    !!filters.source?.[0] ||
    !!filters.tags?.[0] ||
    !!filters.file_extension?.[0];

  function toggleFileType(value: string) {
    const cur = filters.file_type ?? [];
    const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    onChange({ ...filters, file_type: next.length ? next : undefined });
  }

  function toggleTranslation(value: string) {
    const cur = filters.translation_quality ?? [];
    const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    onChange({ ...filters, translation_quality: next.length ? next : undefined });
  }

  function setCsvField(field: "source" | "tags" | "file_extension", raw: string) {
    const values = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    onChange({ ...filters, [field]: values.length ? values : undefined });
  }

  function getCsvField(field: "source" | "tags" | "file_extension"): string {
    return (filters[field] ?? []).join(", ");
  }

  return (
    <aside className={styles.panel} aria-label={t.filters.panel}>
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionLabel}>{t.filters.fileType}</span>
          {(filters.file_type?.length ?? 0) > 0 && (
            <button
              className={styles.clearBtn}
              onClick={() => onChange({ ...filters, file_type: undefined })}
            >
              {t.filters.clear}
            </button>
          )}
        </div>
        <div className={styles.options}>
          {FILE_TYPES.map(({ value, label }) => (
            <label key={value} className={styles.option}>
              <input
                type="checkbox"
                checked={(filters.file_type ?? []).includes(value)}
                onChange={() => toggleFileType(value)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionLabel}>{t.filters.translation}</span>
          {(filters.translation_quality?.length ?? 0) > 0 && (
            <button
              className={styles.clearBtn}
              onClick={() => onChange({ ...filters, translation_quality: undefined })}
            >
              {t.filters.clear}
            </button>
          )}
        </div>
        <div className={styles.options}>
          {TRANSLATION_OPTS.map(({ value, label }) => (
            <label key={value} className={styles.option}>
              <input
                type="checkbox"
                checked={(filters.translation_quality ?? []).includes(value)}
                onChange={() => toggleTranslation(value)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {/* Sort */}
      <div className={styles.section}>
        <label className={styles.sectionLabel}>Sort by</label>
        <select
          className={styles.select}
          value={filters.sort_by ?? "relevance"}
          onChange={(e) =>
            onChange({ ...filters, sort_by: e.target.value as SearchFilters["sort_by"] })
          }
        >
          {SORT_OPTS.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      {/* Advanced */}
      <div className={styles.section}>
        <button
          type="button"
          className={styles.advancedToggle}
          aria-expanded={advancedOpen}
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          Advanced
        </button>
        {advancedOpen && (
          <div className={styles.advancedBody}>
            <label className={styles.fieldLabel}>
              Source
              <input
                type="text"
                className={styles.textInput}
                value={getCsvField("source")}
                onChange={(e) => setCsvField("source", e.target.value)}
                placeholder="folder, nifi"
              />
            </label>
            <label className={styles.fieldLabel}>
              Tags
              <input
                type="text"
                className={styles.textInput}
                value={getCsvField("tags")}
                onChange={(e) => setCsvField("tags", e.target.value)}
                placeholder="contract, legal"
              />
            </label>
            <label className={styles.fieldLabel}>
              Extension
              <input
                type="text"
                className={styles.textInput}
                value={getCsvField("file_extension")}
                onChange={(e) => setCsvField("file_extension", e.target.value)}
                placeholder="pdf, docx"
              />
            </label>
          </div>
        )}
      </div>

      <div className={styles.section}>
        <label className={styles.option}>
          <input
            type="checkbox"
            checked={!!filters.include_older_versions}
            onChange={(e) =>
              onChange({ ...filters, include_older_versions: e.target.checked || undefined })
            }
          />
          {t.filters.includeOlderVersions}
        </label>
      </div>

      {hasAny && (
        <div className={styles.clearAll}>
          <button className={styles.clearAllBtn} onClick={() => onChange({})}>
            {t.filters.clearAll}
          </button>
        </div>
      )}
    </aside>
  );
}
