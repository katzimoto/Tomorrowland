import styles from "./Skeleton.module.css";

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  className?: string;
  rounded?: boolean;
}

export function Skeleton({ width, height, className = "", rounded = false }: SkeletonProps) {
  return (
    <span
      className={`${styles.skeleton} ${rounded ? styles.rounded : ""} ${className}`}
      style={{ width, height }}
      aria-hidden
    />
  );
}

interface SkeletonRowProps {
  /** Number of skeleton rows to render. Each row reserves --result-row-height. */
  count?: number;
  compact?: boolean;
  className?: string;
}

/** Renders placeholder rows that exactly match the reserved result-row height.
 * Prevents layout jumps when real content loads. */
export function SkeletonRow({ count = 3, compact = false, className = "" }: SkeletonRowProps) {
  return (
    <div className={className} aria-label="Loading" aria-live="polite">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`${styles.row} ${compact ? styles.compact : ""}`}
        >
          {/* Icon placeholder */}
          <Skeleton width={36} height={36} rounded className={styles.rowIcon} />
          {/* Text lines */}
          <div className={styles.rowLines}>
            <Skeleton height={14} width={i % 3 === 0 ? "55%" : i % 3 === 1 ? "70%" : "60%"} />
            <Skeleton height={12} width={i % 2 === 0 ? "85%" : "75%"} />
            <Skeleton height={12} width="40%" />
          </div>
          {/* Right-side meta placeholder */}
          <div className={styles.rowMeta}>
            <Skeleton height={12} width={52} />
            <Skeleton height={20} width={36} className={styles.rowBadge} />
          </div>
        </div>
      ))}
    </div>
  );
}
