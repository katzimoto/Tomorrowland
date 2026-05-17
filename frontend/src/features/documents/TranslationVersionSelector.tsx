import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTranslationVersions, type TranslationVersion } from "@/api/documents";
import styles from "./TranslationVersionSelector.module.css";

const POLL_INTERVAL_MS = 5000;

interface TranslationVersionSelectorProps {
  docId: string;
  selectedVersionId: string | undefined;
  showOriginal: boolean;
  onSelect: (versionId: string | undefined) => void;
  onShowOriginalChange: (showOriginal: boolean) => void;
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
  showOriginal,
  onSelect,
  onShowOriginalChange,
}: TranslationVersionSelectorProps) {
  const hadInProgressRef = useRef(false);
  const initialSelectDoneRef = useRef(false);

  const { data: versions } = useQuery({
    queryKey: ["doc-translation-versions", docId],
    queryFn: () => getTranslationVersions(docId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && hasInProgressVersions(data) ? POLL_INTERVAL_MS : false;
    },
  });

  // Auto-select the latest available translation version:
  // - on initial load when translations are already available, and
  // - when a pending/running translation completes.
  useEffect(() => {
    if (!versions) return;
    if (selectedVersionId !== undefined) return;
    if (showOriginal) return;
    if (hasInProgressVersions(versions)) {
      hadInProgressRef.current = true;
      return;
    }
    const latestAvailable = [...versions]
      .filter((v) => v.status === "available")
      .sort((a, b) => b.version_number - a.version_number)[0];
    if (hadInProgressRef.current) {
      hadInProgressRef.current = false;
      if (latestAvailable) {
        onSelect(latestAvailable.version_id);
      }
      return;
    }
    if (!initialSelectDoneRef.current && latestAvailable) {
      initialSelectDoneRef.current = true;
      onSelect(latestAvailable.version_id);
    }
  }, [versions, selectedVersionId, showOriginal, onSelect]);

  if (!versions?.length) return null;

  const currentValue = showOriginal ? "__original__" : (selectedVersionId ?? "");

  return (
    <label className={styles.wrapper}>
      <span className={styles.label}>Version</span>
      <select
        className={styles.select}
        value={currentValue}
        onChange={(e) => {
          const val = e.target.value;
          if (val === "__original__") {
            onShowOriginalChange(true);
          } else {
            onShowOriginalChange(false);
            onSelect(val || undefined);
          }
        }}
        aria-label="Translation version"
      >
        <option value="">Latest</option>
        <option value="__original__">Original</option>
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
