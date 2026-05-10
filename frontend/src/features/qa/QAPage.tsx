import { QAPanel } from "./QAPanel";
import styles from "./QAPage.module.css";

export function QAPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Q&amp;A</h1>
      </header>
      <div className={styles.body}>
        <QAPanel returnPath="/qa" />
      </div>
    </div>
  );
}
