import { useEffect, useRef } from "react";
import { X, ChevronUp, ChevronDown } from "lucide-react";
import styles from "./DocumentSearchBar.module.css";

interface DocumentSearchBarProps {
  query: string;
  matchCount: number;
  activeIndex: number;
  onQueryChange: (q: string) => void;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
}

export function DocumentSearchBar({
  query,
  matchCount,
  activeIndex,
  onQueryChange,
  onNext,
  onPrev,
  onClose,
}: DocumentSearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when bar mounts
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "Enter") {
      e.shiftKey ? onPrev() : onNext();
    }
  }

  const counterText =
    matchCount === 0
      ? query ? "No results" : ""
      : `${activeIndex + 1} of ${matchCount}`;

  return (
    <div className={styles.bar} role="search">
      <input
        ref={inputRef}
        className={styles.input}
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="Search within document"
        placeholder="Find in document…"
        spellCheck={false}
      />
      <span
        className={styles.counter}
        aria-live="polite"
        aria-atomic="true"
      >
        {counterText}
      </span>
      <button
        className={styles.navBtn}
        aria-label="Previous match"
        disabled={matchCount === 0}
        onClick={onPrev}
      >
        <ChevronUp size={14} />
      </button>
      <button
        className={styles.navBtn}
        aria-label="Next match"
        disabled={matchCount === 0}
        onClick={onNext}
      >
        <ChevronDown size={14} />
      </button>
      <button
        className={styles.closeBtn}
        aria-label="Close search"
        onClick={onClose}
      >
        <X size={14} />
      </button>
    </div>
  );
}
