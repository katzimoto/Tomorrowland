import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTranslationVersions, type TranslationVersion } from "@/api/documents";
import styles from "./TranslationVersionSelector.module.css";

const POLL_INTERVAL_MS = 5000;

interface TranslationVersionSelectorProps {
  docId: string;
  selectedVersionId: string | undefined;
  onSelect: (versionId: string | undefined) => void;
}

function isSelectableTranslationVersion(status: TranslationVersion["status"]): boolean {
  return status === "available";
}

function hasInProgressVersions(versions: TranslationVersion[]): boolean {
  return versions.some((v) => v.status === "pending" || v.status === "running");
}

export function TranslationVersionSelector({
  docId,
  selectedVersionId,
  onSelect,
}: TranslationVersionSelectorProps) {
  const hadInProgressRef = useRef(false);

  const { data: versions } = useQuery({
    queryKey: ["doc-translation-versions", docId],
    queryFn: () => getTranslationVersions(docId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && hasInProgressVersions(data) ? POLL_INTERVAL_MS : false;
    },
  });

  // When a pending/running translation completes, auto-select the latest available version
  // so the preview switches to the translated content without requiring a manual action.
  useEffect(() => {
    if (!versions) return;
    if (selectedVersionId !== undefined) return;
    if (hasInProgressVersions(versions)) {
      hadInProgressRef.current = true;
      return;
    }
    if (hadInProgressRef.current) {
      hadInProgressRef.current = false;
      const latestAvailable = [...versions]
        .filter((v) => v.status === "available")
        .sort((a, b) => b.version_number - a.version_number)[0];
      if (latestAvailable) {
        onSelect(latestAvailable.version_id);
      }
    }
  }, [versions, selectedVersionId, onSelect]);

  if (!versions?.length) return null;

  return (
    <label className={styles.wrapper}>
      <span className={styles.label}>Version</span>
      <select
        className={styles.select}
        value={selectedVersionId ?? ""}
        onChange={(e) => onSelect(e.target.value || undefined)}
        aria-label="Translation version"
      >
        <option value="">Latest</option>
        {versions.map((v: TranslationVersion) => {
          const isSelectable = isSelectableTranslationVersion(v.status);
          return (
            <option
              key={v.version_id}
              value={v.version_id}
              disabled={!isSelectable}
            >
              {v.label} {!isSelectable ? `(${v.status})` : ""}
            </option>
          );
        })}
      </select>
    </label>
  );
}
