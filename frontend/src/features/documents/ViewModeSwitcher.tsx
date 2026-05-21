import styles from "./ViewModeSwitcher.module.css";

export type ViewMode = "original" | "extracted" | "translation";

interface ViewModeSwitcherProps {
  availableModes: ViewMode[];
  activeMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

const MODE_LABELS: Record<ViewMode, string> = {
  original: "Original",
  extracted: "Extracted",
  translation: "Translation",
};

export function ViewModeSwitcher({
  availableModes,
  activeMode,
  onModeChange,
}: ViewModeSwitcherProps) {
  if (availableModes.length <= 1) return null;

  return (
    <div className={styles.switcher} role="group" aria-label="View mode">
      {availableModes.map((mode) => (
        <button
          key={mode}
          className={`${styles.btn} ${activeMode === mode ? styles.active : ""}`}
          aria-pressed={activeMode === mode}
          onClick={() => onModeChange(mode)}
        >
          {MODE_LABELS[mode]}
        </button>
      ))}
    </div>
  );
}
