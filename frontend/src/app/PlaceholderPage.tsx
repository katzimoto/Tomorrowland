import styles from "./PlaceholderPage.module.css";

interface PlaceholderPageProps {
  title: string;
}

export function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>{title}</h1>
      <p className={styles.body}>This page will be implemented in Phase 08c.</p>
    </div>
  );
}
