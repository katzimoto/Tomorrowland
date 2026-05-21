import { startTransition, useEffect, useRef, useState } from "react";
import { UnsupportedPreview } from "./UnsupportedPreview";
import { ExtractionFailedPreview } from "./ExtractionFailedPreview";
import {
  finishNamedPerformanceTimer,
  startNamedPerformanceTimer,
} from "@/lib/performanceTelemetry";
import styles from "./ImageViewer.module.css";

const ZOOM_STEPS = [25, 50, 75, 100, 125, 150, 200, 300, 400];
const PAN_STEP = 40;

function nextStep(zoom: number): number {
  const above = ZOOM_STEPS.filter((s) => s > zoom);
  return above.length ? above[0] : zoom;
}

function prevStep(zoom: number): number {
  const below = ZOOM_STEPS.filter((s) => s < zoom);
  return below.length ? below[below.length - 1] : zoom;
}

function clampZoom(z: number): number {
  return Math.min(Math.max(z, ZOOM_STEPS[0]), ZOOM_STEPS[ZOOM_STEPS.length - 1]);
}

interface ImageViewerProps {
  docId: string;
  mimeType: string;
  alt: string;
  zoom: number | null;
  onZoomChange: (zoom: number | null) => void;
}

export function ImageViewer({ docId, mimeType, alt, zoom, onZoomChange }: ImageViewerProps) {
  const src = `/api/download/${docId}`;
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [dimensions, setDimensions] = useState<{ w: number; h: number } | null>(null);
  const dragRef = useRef<{ active: boolean; startX: number; startY: number; origX: number; origY: number }>({
    active: false, startX: 0, startY: 0, origX: 0, origY: 0,
  });
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset pan when zoom changes.
  useEffect(() => {
    startTransition(() => { setPan({ x: 0, y: 0 }); });
  }, [zoom]);

  const imageLoadTimer = useRef<string | null>(null);
  useEffect(() => {
    if (mimeType !== "image/tiff" && !imageLoadTimer.current) {
      imageLoadTimer.current = `image-load-${Date.now()}`;
      startNamedPerformanceTimer(imageLoadTimer.current);
    }
  }, [mimeType]);

  if (mimeType === "image/tiff") {
    return <UnsupportedPreview mimeType={mimeType} downloadUrl={src} />;
  }

  function handleLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    setLoading(false);
    const img = e.currentTarget;
    setDimensions({ w: img.naturalWidth, h: img.naturalHeight });
    if (imageLoadTimer.current) {
      finishNamedPerformanceTimer(imageLoadTimer.current, "viewer.image.load", "success");
      imageLoadTimer.current = null;
    }
  }

  function handleError() {
    setLoading(false);
    setError(true);
  }

  function handlePointerDown(e: React.PointerEvent) {
    if (zoom === null) return;
    dragRef.current = { active: true, startX: e.clientX, startY: e.clientY, origX: pan.x, origY: pan.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function handlePointerMove(e: React.PointerEvent) {
    if (!dragRef.current.active) return;
    setPan({
      x: dragRef.current.origX + (e.clientX - dragRef.current.startX),
      y: dragRef.current.origY + (e.clientY - dragRef.current.startY),
    });
  }

  function handlePointerUp() {
    dragRef.current.active = false;
  }

  function handleWheel(e: React.WheelEvent) {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const current = zoom ?? 100;
    const delta = e.deltaY > 0 ? -10 : 10;
    const next = clampZoom(current + delta);
    onZoomChange(next <= 20 ? null : next);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    switch (e.key) {
      case "+":
      case "=":
        e.preventDefault();
        onZoomChange(zoom === null ? 100 : nextStep(zoom));
        break;
      case "-":
        e.preventDefault();
        if (zoom === null || zoom <= ZOOM_STEPS[0]) {
          onZoomChange(null);
        } else {
          onZoomChange(prevStep(zoom));
        }
        break;
      case "0":
        e.preventDefault();
        onZoomChange(null);
        break;
      case "ArrowLeft":
        if (zoom !== null) { e.preventDefault(); setPan((p) => ({ ...p, x: p.x + PAN_STEP })); }
        break;
      case "ArrowRight":
        if (zoom !== null) { e.preventDefault(); setPan((p) => ({ ...p, x: p.x - PAN_STEP })); }
        break;
      case "ArrowUp":
        if (zoom !== null) { e.preventDefault(); setPan((p) => ({ ...p, y: p.y + PAN_STEP })); }
        break;
      case "ArrowDown":
        if (zoom !== null) { e.preventDefault(); setPan((p) => ({ ...p, y: p.y - PAN_STEP })); }
        break;
    }
  }

  function handleDoubleClick() {
    onZoomChange(null);
  }

  const zoomLabel = zoom === null ? "Fit" : `${zoom}%`;

  const imgStyle: React.CSSProperties =
    zoom === null
      ? {}
      : {
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${zoom / 100})`,
          transformOrigin: "center center",
          maxWidth: "none",
          maxHeight: "none",
          userSelect: "none",
        };

  return (
    <div className={styles.outer}>
      <div
        ref={containerRef}
        className={`${styles.container} ${zoom !== null ? styles.zoomed : ""}`}
        tabIndex={0}
        role="img"
        aria-label={alt || "Document image"}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onWheel={handleWheel}
        onKeyDown={handleKeyDown}
        onDoubleClick={handleDoubleClick}
      >
        {loading && <div className={styles.loading}>Loading image…</div>}
        {error ? (
          <ExtractionFailedPreview downloadUrl={src} />
        ) : (
          <img
            src={src}
            alt={alt}
            className={`${styles.img} ${zoom === null ? styles.fit : ""}`}
            style={imgStyle}
            onLoad={handleLoad}
            onError={handleError}
            draggable={false}
          />
        )}
      </div>

      <div className={styles.infoBar} aria-live="polite">
        {dimensions && (
          <span>
            {dimensions.w} × {dimensions.h}
            {" — "}
          </span>
        )}
        <span>{zoomLabel}</span>
        <span className={styles.hint} aria-hidden="true">
          {" · "}+/- zoom · 0 fit · drag to pan
        </span>
      </div>

      <p className={styles.srOnly}>
        Keyboard controls: plus or minus to zoom, zero to fit, arrow keys to pan, Ctrl and scroll to zoom.
      </p>
    </div>
  );
}
