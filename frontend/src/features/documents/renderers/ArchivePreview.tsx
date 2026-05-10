import styles from "./renderers.module.css";

interface ArchivePreviewProps {
  text: string;
}

export function ArchivePreview({ text }: ArchivePreviewProps) {
  const filenames = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  if (!filenames.length) {
    return <p className={styles.muted}>Archive is empty.</p>;
  }

  return (
    <ul className={styles.archiveList} aria-label="Archive contents">
      {filenames.map((name, i) => (
        <li key={i} className={styles.archiveItem}>{name}</li>
      ))}
    </ul>
  );
}
