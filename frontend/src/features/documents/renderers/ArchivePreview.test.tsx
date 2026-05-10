import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { ArchivePreview } from "./ArchivePreview";

describe("ArchivePreview", () => {
  it("renders archive file list", () => {
    render(<ArchivePreview text={"README.md\nsrc/main.py\ntests/test_main.py"} />);
    expect(screen.getByText("README.md")).toBeInTheDocument();
    expect(screen.getByText("src/main.py")).toBeInTheDocument();
  });

  it("shows empty state for blank text", () => {
    render(<ArchivePreview text="" />);
    expect(screen.getByText("Archive is empty.")).toBeInTheDocument();
  });
});
