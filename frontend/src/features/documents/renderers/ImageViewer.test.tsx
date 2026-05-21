import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ImageViewer } from "./ImageViewer";

function setup(overrides: Partial<Parameters<typeof ImageViewer>[0]> = {}) {
  const onZoomChange = vi.fn();
  const utils = render(
    <ImageViewer
      docId="doc-1"
      mimeType="image/png"
      alt="Test image"
      zoom={null}
      onZoomChange={onZoomChange}
      {...overrides}
    />
  );
  return { ...utils, onZoomChange };
}

describe("ImageViewer", () => {
  it("renders img with correct src", () => {
    setup();
    const img = document.querySelector("img");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", "/api/download/doc-1");
  });

  it("renders img with the provided alt text", () => {
    setup({ alt: "My document" });
    const img = document.querySelector("img");
    expect(img).toHaveAttribute("alt", "My document");
  });

  it("shows loading state initially", () => {
    setup();
    expect(screen.getByText("Loading image…")).toBeInTheDocument();
  });

  it("hides loading text after image load", () => {
    setup();
    const img = document.querySelector("img")!;
    fireEvent.load(img);
    expect(screen.queryByText("Loading image…")).not.toBeInTheDocument();
  });

  it("shows ExtractionFailedPreview on image load error", () => {
    setup();
    const img = document.querySelector("img")!;
    fireEvent.error(img);
    expect(screen.getByText("Text extraction failed")).toBeInTheDocument();
  });

  it("shows UnsupportedPreview for TIFF", () => {
    setup({ mimeType: "image/tiff" });
    expect(screen.getByText("Preview not available")).toBeInTheDocument();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("SVG renders as img, not inline svg", () => {
    setup({ mimeType: "image/svg+xml" });
    expect(document.querySelector("img")).toBeInTheDocument();
    expect(document.querySelector("svg")).not.toBeInTheDocument();
  });

  it("shows dimensions after image loads", () => {
    setup();
    const img = document.querySelector("img")!;
    Object.defineProperty(img, "naturalWidth", { value: 800 });
    Object.defineProperty(img, "naturalHeight", { value: 600 });
    fireEvent.load(img);
    expect(screen.getByText(/800 × 600/)).toBeInTheDocument();
  });

  it("shows Fit when zoom is null", () => {
    setup({ zoom: null });
    expect(screen.getByText("Fit")).toBeInTheDocument();
  });

  it("shows zoom percentage when zoom is set", () => {
    setup({ zoom: 125 });
    expect(screen.getByText("125%")).toBeInTheDocument();
  });

  it("zoom in button calls onZoomChange with next step", () => {
    // ImageViewer doesn't have zoom buttons — those are in DocumentToolbar.
    // Keyboard '+' is the ImageViewer-level control.
    const onZoomChange = vi.fn();
    render(
      <ImageViewer
        docId="doc-1"
        mimeType="image/png"
        alt="img"
        zoom={100}
        onZoomChange={onZoomChange}
      />
    );
    const container = document.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(container, { key: "+" });
    expect(onZoomChange).toHaveBeenCalledWith(125);
  });

  it("keyboard - zooms out to previous step", () => {
    const onZoomChange = vi.fn();
    render(
      <ImageViewer
        docId="doc-1"
        mimeType="image/png"
        alt="img"
        zoom={125}
        onZoomChange={onZoomChange}
      />
    );
    const container = document.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(container, { key: "-" });
    expect(onZoomChange).toHaveBeenCalledWith(100);
  });

  it("keyboard - zooms out to fit when at minimum step", () => {
    const onZoomChange = vi.fn();
    render(
      <ImageViewer
        docId="doc-1"
        mimeType="image/png"
        alt="img"
        zoom={25}
        onZoomChange={onZoomChange}
      />
    );
    const container = document.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(container, { key: "-" });
    expect(onZoomChange).toHaveBeenCalledWith(null);
  });

  it("keyboard 0 resets to fit", () => {
    const onZoomChange = vi.fn();
    render(
      <ImageViewer
        docId="doc-1"
        mimeType="image/png"
        alt="img"
        zoom={200}
        onZoomChange={onZoomChange}
      />
    );
    const container = document.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(container, { key: "0" });
    expect(onZoomChange).toHaveBeenCalledWith(null);
  });

  it("double-click resets to fit", () => {
    const onZoomChange = vi.fn();
    render(
      <ImageViewer
        docId="doc-1"
        mimeType="image/png"
        alt="img"
        zoom={200}
        onZoomChange={onZoomChange}
      />
    );
    const container = document.querySelector("[tabindex]") as HTMLElement;
    fireEvent.dblClick(container);
    expect(onZoomChange).toHaveBeenCalledWith(null);
  });

  it("keyboard + in fit mode goes to 100%", () => {
    const onZoomChange = vi.fn();
    render(
      <ImageViewer
        docId="doc-1"
        mimeType="image/png"
        alt="img"
        zoom={null}
        onZoomChange={onZoomChange}
      />
    );
    const container = document.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(container, { key: "+" });
    expect(onZoomChange).toHaveBeenCalledWith(100);
  });

  it("has accessible keyboard help text", () => {
    setup();
    expect(screen.getByText(/Keyboard controls/i)).toBeInTheDocument();
  });

  it("uses empty alt text when no title is provided", () => {
    setup({ alt: "" });
    const img = document.querySelector("img");
    expect(img).toHaveAttribute("alt", "");
  });

  it("container gets fallback aria-label when alt is empty", () => {
    setup({ alt: "" });
    const container = document.querySelector("[tabindex]");
    expect(container).toHaveAttribute("aria-label", "Document image");
  });
});
