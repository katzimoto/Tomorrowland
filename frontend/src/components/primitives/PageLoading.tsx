import { SkeletonRow } from "./Skeleton";
import styles from "./PageLoading.module.css";

export function PageLoading() {
  return (
    <div className={styles.root}>
      <SkeletonRow count={4} />
    </div>
  );
}
