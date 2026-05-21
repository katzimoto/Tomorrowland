import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MediaPreview } from "./MediaPreview";

vi.mock("./UnsupportedPreview", () => ({
  UnsupportedPreview: ({ mimeType }: { mimeType: string }) => (
    <div data-testid="unsupported-preview" data-mime={mimeType} />
  ),
}));

vi.mock("@/api/documents", () => ({
  getDownloadUrl: (docId: string) => `/api/download/${docId}`,
}));

const baseProps = {
  docId: "doc-1",
  title: "Interview Recording.mp3",
  snippet: "",
};

describe("MediaPreview", () => {
  it("renders <audio> element for audio MIME type", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    expect(document.querySelector("audio")).toBeInTheDocument();
    expect(document.querySelector("video")).not.toBeInTheDocument();
  });

  it("audio element has correct src", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    expect(document.querySelector("audio")).toHaveAttribute("src", "/api/download/doc-1");
  });

  it("audio element has controls attribute", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    expect(document.querySelector("audio")).toHaveAttribute("controls");
  });

  it("audio element has title equal to document title", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    expect(document.querySelector("audio")).toHaveAttribute("title", "Interview Recording.mp3");
  });

  it("renders <video> element for video MIME type", () => {
    render(<MediaPreview {...baseProps} mimeType="video/mp4" title="Demo.mp4" />);
    expect(document.querySelector("video")).toBeInTheDocument();
    expect(document.querySelector("audio")).not.toBeInTheDocument();
  });

  it("video element has controls attribute", () => {
    render(<MediaPreview {...baseProps} mimeType="video/mp4" title="Demo.mp4" />);
    expect(document.querySelector("video")).toHaveAttribute("controls");
  });

  it("video element has title equal to document title", () => {
    render(<MediaPreview {...baseProps} mimeType="video/mp4" title="Demo.mp4" />);
    expect(document.querySelector("video")).toHaveAttribute("title", "Demo.mp4");
  });

  it("shows transcript section when snippet is non-empty", () => {
    render(
      <MediaPreview {...baseProps} mimeType="audio/mpeg" snippet="Hello world transcript." />
    );
    expect(screen.getByText("Transcript / Extracted text")).toBeInTheDocument();
    expect(screen.getByText("Hello world transcript.")).toBeInTheDocument();
  });

  it("hides transcript section when snippet is empty", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" snippet="" />);
    expect(screen.queryByText("Transcript / Extracted text")).not.toBeInTheDocument();
  });

  it("transcript heading is an h3", () => {
    render(
      <MediaPreview {...baseProps} mimeType="audio/mpeg" snippet="Some text." />
    );
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Transcript / Extracted text"
    );
  });

  it("shows MIME type in metadata row", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    expect(screen.getByText("audio/mpeg")).toBeInTheDocument();
  });

  it("shows document title in metadata row", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    expect(screen.getAllByText("Interview Recording.mp3").length).toBeGreaterThan(0);
  });

  it("playback error replaces player with UnsupportedPreview", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    const audioEl = document.querySelector("audio")!;
    fireEvent.error(audioEl);
    expect(screen.getByTestId("unsupported-preview")).toBeInTheDocument();
    expect(document.querySelector("audio")).not.toBeInTheDocument();
  });

  it("UnsupportedPreview receives correct mimeType on error", () => {
    render(<MediaPreview {...baseProps} mimeType="audio/mpeg" />);
    fireEvent.error(document.querySelector("audio")!);
    expect(screen.getByTestId("unsupported-preview")).toHaveAttribute("data-mime", "audio/mpeg");
  });

  it("video error also shows UnsupportedPreview", () => {
    render(<MediaPreview {...baseProps} mimeType="video/mp4" title="Demo.mp4" />);
    fireEvent.error(document.querySelector("video")!);
    expect(screen.getByTestId("unsupported-preview")).toBeInTheDocument();
  });

  it("renders transcript section element", () => {
    render(
      <MediaPreview {...baseProps} mimeType="audio/mpeg" snippet="Words here." />
    );
    expect(document.querySelector("section")).toBeInTheDocument();
  });
});
