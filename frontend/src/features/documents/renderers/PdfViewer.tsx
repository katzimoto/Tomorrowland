import { useEffect, useRef, useState, useMemo } from "react";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { ExtractionFailedPreview } from "./ExtractionFailedPreview";
import { countMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

// Configure worker once — Vite bundles this as a local asset, no CDN required
pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

const DEFAULT_SCALE = 1.2;
const SCALE_STEP = 0.25;
const MIN_SCALE = 0.5;
const MAX_SCALE = 3.0;

interface PdfViewerProps {
  docId: string;
  searchQuery?: string;
  onMatchCountChange?: (count: number) => void;
}

export function PdfViewer({ docId, searchQuery = "", onMatchCountChange }: PdfViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageNum, setPageNum] = useState(1);
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [allPdfText, setAllPdfText] = useState("");

  const downloadUrl = `/api/download/${docId}`;

  // Load PDF document
  useEffect(() => {
    setLoading(true);
    setError(false);
    setPageNum(1);
    setPdfDoc(null);
    const task = pdfjsLib.getDocument(downloadUrl);
    task.promise.then(
      (doc) => {
        setPdfDoc(doc);
        setNumPages(doc.numPages);
        setLoading(false);
      },
      () => {
        setError(true);
        setLoading(false);
      },
    );
    return () => {
      task.destroy();
    };
  }, [downloadUrl]);

  // Extract text from all pages for in-document search
  useEffect(() => {
    if (!pdfDoc) return;
    let cancelled = false;
    async function extractText() {
      if (!pdfDoc) return;
      const parts: string[] = [];
      for (let i = 1; i <= pdfDoc.numPages; i++) {
        const page = await pdfDoc.getPage(i);
        const content = await page.getTextContent();
        const pageText = content.items
          .map((item) => ("str" in item ? item.str : ""))
          .join(" ");
        parts.push(pageText);
      }
      if (!cancelled) setAllPdfText(parts.join(" "));
    }
    void extractText();
    return () => { cancelled = true; };
  }, [pdfDoc]);

  // Report match count when search query or text changes
  const matchCount = useMemo(
    () => countMatches(allPdfText, searchQuery),
    [allPdfText, searchQuery],
  );
  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  // Render current page to canvas
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    let cancelled = false;
    pdfDoc.getPage(pageNum).then((page) => {
      if (cancelled || !canvasRef.current) return;
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      void page.render({ canvasContext: ctx, viewport }).promise;
    });
    return () => {
      cancelled = true;
    };
  }, [pdfDoc, pageNum, scale]);

  if (loading) {
    return <div className={styles.muted}>Loading PDF…</div>;
  }
  if (error) {
    return <ExtractionFailedPreview downloadUrl={downloadUrl} />;
  }

  return (
    <div className={styles.pdfWrapper}>
      <div className={styles.pdfControls}>
        <button
          className={styles.pdfBtn}
          aria-label="Previous page"
          disabled={pageNum <= 1}
          onClick={() => setPageNum((n) => Math.max(1, n - 1))}
        >
          ‹
        </button>
        <span className={styles.pdfPageInfo} aria-live="polite">
          {pageNum} / {numPages}
        </span>
        <button
          className={styles.pdfBtn}
          aria-label="Next page"
          disabled={pageNum >= numPages}
          onClick={() => setPageNum((n) => Math.min(numPages, n + 1))}
        >
          ›
        </button>
        <span className={styles.pdfDivider} aria-hidden="true" />
        <button
          className={styles.pdfBtn}
          aria-label="Zoom in"
          disabled={scale >= MAX_SCALE}
          onClick={() =>
            setScale((s) => Math.min(MAX_SCALE, +(s + SCALE_STEP).toFixed(2)))
          }
        >
          +
        </button>
        <button
          className={styles.pdfBtn}
          aria-label="Zoom out"
          disabled={scale <= MIN_SCALE}
          onClick={() =>
            setScale((s) => Math.max(MIN_SCALE, +(s - SCALE_STEP).toFixed(2)))
          }
        >
          −
        </button>
        <button
          className={styles.pdfBtn}
          aria-label="Reset zoom"
          onClick={() => setScale(DEFAULT_SCALE)}
        >
          ↺
        </button>
      </div>
      <div
        className={styles.pdfCanvasWrapper}
        role="document"
        aria-label={`PDF page ${pageNum} of ${numPages}`}
      >
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
