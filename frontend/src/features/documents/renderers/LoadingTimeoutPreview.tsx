import { Clock } from "lucide-react";
import styles from "./renderers.module.css";

interface LoadingTimeoutPreviewProps {
  onRetry: () => void;
}

export function LoadingTimeoutPreview({ onRetry }: LoadingTimeoutPreviewProps) {
  return (
    <div className={styles.fallback} role="status">
      <Clock size={32} className={styles.fallbackIcon} />
      <p className={styles.fallbackTitle}>Preview is taking longer than expected</p>
      <p className={styles.fallbackBody}>
        The document may still be processing. Try again in a moment.
      </p>
      <button onClick={onRetry} className={styles.fallbackAction}>
        Retry
      </button>
    </div>
  );
}
