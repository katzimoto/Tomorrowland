import type { ViewMode } from "./ViewModeSwitcher";
import styles from "./FidelityStatusBar.module.css";

interface FidelityStatusBarProps {
  activeMode: ViewMode;
  translationQuality: "fast" | "high" | null;
  downloadUrl: string;
}

type DotColor = "green" | "amber";

interface StatusDescriptor {
  dot: DotColor;
  text: string;
  includesDownload: boolean;
}

function getStatus(
  activeMode: ViewMode,
  translationQuality: "fast" | "high" | null
): StatusDescriptor {
  if (activeMode === "original") {
    return { dot: "green", text: "Viewing original file", includesDownload: false };
  }
  if (activeMode === "extracted") {
    return {
      dot: "amber",
      text: "Viewing extracted text",
      includesDownload: true,
    };
  }
  // translation mode
  if (translationQuality === "high") {
    return {
      dot: "green",
      text: "Viewing high-quality translation",
      includesDownload: false,
    };
  }
  if (translationQuality === "fast") {
    return {
      dot: "amber",
      text: "Viewing fast translation",
      includesDownload: true,
    };
  }
  return {
    dot: "amber",
    text: "Viewing extracted text",
    includesDownload: true,
  };
}

const DOT_LABELS: Record<DotColor, string> = {
  green: "Good",
  amber: "Info",
};

export function FidelityStatusBar({
  activeMode,
  translationQuality,
  downloadUrl,
}: FidelityStatusBarProps) {
  const { dot, text, includesDownload } = getStatus(activeMode, translationQuality);

  return (
    <div className={styles.bar}>
      <span
        className={`${styles.dot} ${styles[dot]}`}
        role="img"
        aria-label={DOT_LABELS[dot]}
      />
      <span className={styles.text}>
        {text}
        {includesDownload && (
          <>
            {" — "}
            <a href={downloadUrl} download className={styles.link}>
              download original
            </a>
            {" to view source"}
          </>
        )}
      </span>
    </div>
  );
}
