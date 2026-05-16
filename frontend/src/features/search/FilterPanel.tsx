import type { SearchFilters } from "@/api/search";
import { useT } from "@/i18n/index";
import styles from "./FilterPanel.module.css";

interface FilterPanelProps {
  filters: SearchFilters;
  onChange: (f: SearchFilters) => void;
}

export function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const t = useT();

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

  const hasAny =
    (filters.file_type?.length ?? 0) > 0 ||
    (filters.translation_quality?.length ?? 0) > 0 ||
    !!filters.date_from ||
    !!filters.include_older_versions;

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
    <aside className={styles.panel} aria-label={t.filters.panel}>
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionLabel}>{t.filters.fileType}</span>
          {(filters.file_type?.length ?? 0) > 0 && (
            <button className={styles.clearBtn} onClick={() => onChange({ ...filters, file_type: undefined })}>
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
            <button className={styles.clearBtn} onClick={() => onChange({ ...filters, translation_quality: undefined })}>
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

      <div className={styles.section}>
        <label className={styles.option}>
          <input
            type="checkbox"
            checked={!!filters.include_older_versions}
            onChange={(e) => onChange({ ...filters, include_older_versions: e.target.checked || undefined })}
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
