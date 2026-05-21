import { useState } from "react";
import { getDownloadUrl } from "@/api/documents";
import { UnsupportedPreview } from "./UnsupportedPreview";
import styles from "./MediaPreview.module.css";

interface MediaPreviewProps {
  docId: string;
  mimeType: string;
  title: string | null;
  snippet: string;
}

export function MediaPreview({ docId, mimeType, title, snippet }: MediaPreviewProps) {
  const [mediaError, setMediaError] = useState(false);
  const src = getDownloadUrl(docId);
  const isVideo = mimeType.startsWith("video/");

  if (mediaError) {
    return <UnsupportedPreview mimeType={mimeType} downloadUrl={src} />;
  }

  return (
    <div className={styles.wrapper}>
      {isVideo ? (
        <div className={styles.videoContainer}>
          <video
            className={styles.video}
            controls
            src={src}
            title={title ?? undefined}
            onError={() => setMediaError(true)}
          />
        </div>
      ) : (
        <audio
          className={styles.audio}
          controls
          src={src}
          title={title ?? undefined}
          onError={() => setMediaError(true)}
        />
      )}

      <div className={styles.meta}>
        {title && <span className={styles.metaItem}>{title}</span>}
        <span className={styles.metaItem}>
          <code className={styles.metaCode}>{mimeType}</code>
        </span>
      </div>

      {snippet && (
        <section className={styles.transcript}>
          <h3 className={styles.transcriptHeading}>Transcript / Extracted text</h3>
          <p className={styles.transcriptBody}>{snippet}</p>
        </section>
      )}
    </div>
  );
}
