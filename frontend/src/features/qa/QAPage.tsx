import { useT } from "@/i18n/index";
import { QAPanel } from "./QAPanel";
import styles from "./QAPage.module.css";

export function QAPage() {
  const t = useT();
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t.qa.title}</h1>
      </header>
      <div className={styles.body}>
        <QAPanel returnPath="/qa" />
      </div>
    </div>
  );
}
