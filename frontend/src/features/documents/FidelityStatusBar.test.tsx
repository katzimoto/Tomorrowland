import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FidelityStatusBar } from "./FidelityStatusBar";

describe("FidelityStatusBar", () => {
  it("shows 'Viewing original file' in original mode", () => {
    render(
      <FidelityStatusBar
        activeMode="original"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByText(/Viewing original file/i)).toBeInTheDocument();
  });

  it("does not show download button in original mode", () => {
    render(
      <FidelityStatusBar
        activeMode="original"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.queryByRole("button", { name: /download original/i })).not.toBeInTheDocument();
  });

  it("shows 'Viewing extracted text' in extracted mode", () => {
    render(
      <FidelityStatusBar
        activeMode="extracted"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByText(/Viewing extracted text/)).toBeInTheDocument();
  });

  it("shows download button in extracted mode", () => {
    render(
      <FidelityStatusBar
        activeMode="extracted"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(
      screen.getByRole("button", { name: /download original/i })
    ).toBeInTheDocument();
  });

  it("shows 'Viewing high-quality translation' for translation+high", () => {
    render(
      <FidelityStatusBar
        activeMode="translation"
        translationQuality="high"
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByText(/Viewing high-quality translation/)).toBeInTheDocument();
  });

  it("does not show download button for high-quality translation", () => {
    render(
      <FidelityStatusBar
        activeMode="translation"
        translationQuality="high"
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.queryByRole("button", { name: /download original/i })).not.toBeInTheDocument();
  });

  it("shows 'Viewing fast translation' for translation+fast", () => {
    render(
      <FidelityStatusBar
        activeMode="translation"
        translationQuality="fast"
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByText(/Viewing fast translation/)).toBeInTheDocument();
  });

  it("shows download button for fast translation", () => {
    render(
      <FidelityStatusBar
        activeMode="translation"
        translationQuality="fast"
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(
      screen.getByRole("button", { name: /download original/i })
    ).toBeInTheDocument();
  });

  it("dot has an accessible label (not colour alone)", () => {
    render(
      <FidelityStatusBar
        activeMode="original"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByRole("img")).toHaveAttribute("aria-label");
  });

  it("dot label differs between green and amber status", () => {
    const { rerender } = render(
      <FidelityStatusBar
        activeMode="original"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    const greenLabel = screen.getByRole("img").getAttribute("aria-label");

    rerender(
      <FidelityStatusBar
        activeMode="extracted"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    const amberLabel = screen.getByRole("img").getAttribute("aria-label");

    expect(greenLabel).not.toBe(amberLabel);
  });

  it("has visually hidden status text alongside the dot", () => {
    render(
      <FidelityStatusBar
        activeMode="original"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByText("OK:")).toBeInTheDocument();
  });

  it("amber status has visually hidden 'Info:' text", () => {
    render(
      <FidelityStatusBar
        activeMode="extracted"
        translationQuality={null}
        downloadUrl="/api/download/doc-1"
      />
    );
    expect(screen.getByText("Info:")).toBeInTheDocument();
  });
});
