import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { countMatches, highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

interface SlidesPreviewProps {
  text: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

export function SlidesPreview({ text, searchQuery = "", activeSearchIndex = 0, onMatchCountChange }: SlidesPreviewProps) {
  const slides = text.split(/\n---+\n/).filter(Boolean);
  const [index, setIndex] = useState(0);
  const current = slides[index] ?? "";

  const matchCount = useMemo(
    () => countMatches(text, searchQuery),
    [text, searchQuery],
  );
  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  const { nodes: contentNodes } = useMemo(
    () => highlightMatches(current, searchQuery, activeSearchIndex, styles.match, styles.activeMatch),
    [current, searchQuery, activeSearchIndex],
  );

  if (!slides.length) {
    return <p className={styles.muted}>No slide content available.</p>;
  }

  return (
    <div className={styles.slidesWrapper}>
      <div className={styles.slide}>
        <pre className={styles.slideContent}>{searchQuery ? contentNodes : current}</pre>
      </div>
      <div className={styles.slideNav}>
        <button
          className={styles.slideBtn}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
          aria-label="Previous slide"
        >
          <ChevronLeft size={16} />
        </button>
        <span className={styles.slideCount}>{index + 1} / {slides.length}</span>
        <button
          className={styles.slideBtn}
          onClick={() => setIndex((i) => Math.min(slides.length - 1, i + 1))}
          disabled={index === slides.length - 1}
          aria-label="Next slide"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
