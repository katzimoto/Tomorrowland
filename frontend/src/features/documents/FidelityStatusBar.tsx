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
  green: "OK",
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
      <span className={styles.srOnly}>{DOT_LABELS[dot]}: </span>
      <span className={styles.text}>
        {text}
        {includesDownload && (
          <>
            {" — "}
            <button
              className={styles.link}
              onClick={() => {
                const token = sessionStorage.getItem("tomorrowland_token");
                const url = downloadUrl;
                fetch(url, { headers: { Authorization: `Bearer ${token || ""}` } })
                  .then((r) => r.blob())
                  .then((blob) => {
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(blob);
                    a.download = blob.type === "application/json" ? "download.bin" : (url.split("/").pop() || "download");
                    a.click();
                    URL.revokeObjectURL(a.href);
                  });
              }}
            >
              download original
            </button>
            {" to view source"}
          </>
        )}
      </span>
    </div>
  );
}
