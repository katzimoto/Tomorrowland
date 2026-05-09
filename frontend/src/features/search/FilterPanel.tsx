import type { SearchFilters } from "@/api/search";
import styles from "./FilterPanel.module.css";

const FILE_TYPES = [
  { value: "application/pdf", label: "PDF" },
  { value: "application/msword", label: "Office" },
  { value: "message/rfc822", label: "Email" },
  { value: "application/zip", label: "Archive" },
  { value: "text/plain", label: "Text" },
  { value: "image/", label: "Image" },
];

const TRANSLATION_OPTS = [
  { value: "fast", label: "Fast translation" },
  { value: "high", label: "High quality" },
];

interface FilterPanelProps {
  filters: SearchFilters;
  onChange: (f: SearchFilters) => void;
}

export function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const hasAny =
    (filters.file_type?.length ?? 0) > 0 ||
    (filters.translation_quality?.length ?? 0) > 0 ||
    !!filters.date_from;

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

  return (
    <aside className={styles.panel} aria-label="Search filters">
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionLabel}>File type</span>
          {(filters.file_type?.length ?? 0) > 0 && (
            <button className={styles.clearBtn} onClick={() => onChange({ ...filters, file_type: undefined })}>
              Clear
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
          <span className={styles.sectionLabel}>Translation</span>
          {(filters.translation_quality?.length ?? 0) > 0 && (
            <button className={styles.clearBtn} onClick={() => onChange({ ...filters, translation_quality: undefined })}>
              Clear
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

      {hasAny && (
        <div className={styles.clearAll}>
          <button className={styles.clearAllBtn} onClick={() => onChange({})}>
            Clear all filters
          </button>
        </div>
      )}
    </aside>
  );
}
