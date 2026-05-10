import styles from "./renderers.module.css";

interface ImagePreviewProps {
  docId: string;
}

export function ImagePreview({ docId }: ImagePreviewProps) {
  return (
    <div className={styles.imageWrapper}>
      <img
        src={`/api/download/${docId}`}
        alt="Document image"
        className={styles.image}
      />
    </div>
  );
}
