import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

  it("highlights matches when searchQuery is provided", () => {
    render(<ArchivePreview text={"README.md\nsrc/main.py"} searchQuery="main" />);
    const marks = document.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0]?.textContent).toBe("main");
  });

  it("reports match count via onMatchCountChange", async () => {
    const onMatchCountChange = vi.fn();
    render(
      <ArchivePreview
        text={"file1.txt\nfile2.doc\nfile3.txt"}
        searchQuery="txt"
        onMatchCountChange={onMatchCountChange}
      />
    );
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(2);
    });
  });
});
