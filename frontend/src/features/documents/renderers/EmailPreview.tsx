import styles from "./renderers.module.css";

interface EmailPreviewProps {
  text: string;
  metadata: Record<string, unknown>;
}

export function EmailPreview({ text, metadata }: EmailPreviewProps) {
  return (
    <div className={styles.emailWrapper}>
      <dl className={styles.emailHeaders}>
        {Boolean(metadata["from"]) && (
          <>
            <dt className={styles.emailHeaderKey}>From</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["from"])}</dd>
          </>
        )}
        {Boolean(metadata["to"]) && (
          <>
            <dt className={styles.emailHeaderKey}>To</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["to"])}</dd>
          </>
        )}
        {Boolean(metadata["subject"]) && (
          <>
            <dt className={styles.emailHeaderKey}>Subject</dt>
            <dd className={styles.emailHeaderVal}>{String(metadata["subject"])}</dd>
          </>
        )}
      </dl>
      <pre className={styles.emailBody}>{text}</pre>
    </div>
  );
}
