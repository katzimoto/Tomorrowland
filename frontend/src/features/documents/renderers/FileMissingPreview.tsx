import { FolderOpen } from "lucide-react";
import styles from "./renderers.module.css";

export function FileMissingPreview() {
  return (
    <div className={styles.fallback} role="status">
      <FolderOpen size={32} className={styles.fallbackIcon} />
      <p className={styles.fallbackTitle}>File not found</p>
      <p className={styles.fallbackBody}>
        The source file for this document could not be located on the server.
      </p>
    </div>
  );
}
