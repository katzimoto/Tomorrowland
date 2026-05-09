import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import styles from "./renderers.module.css";

interface SlidesPreviewProps {
  text: string;
}

export function SlidesPreview({ text }: SlidesPreviewProps) {
  const slides = text.split(/\n---+\n/).filter(Boolean);
  const [index, setIndex] = useState(0);
  const current = slides[index] ?? "";

  if (!slides.length) {
    return <p className={styles.muted}>No slide content available.</p>;
  }

  return (
    <div className={styles.slidesWrapper}>
      <div className={styles.slide}>
        <pre className={styles.slideContent}>{current}</pre>
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
