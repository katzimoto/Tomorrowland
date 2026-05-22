import { describe, it, expect, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { SlidesPreview } from "./SlidesPreview";

describe("SlidesPreview search", () => {
  it("highlights matches on current slide when searchQuery is provided", () => {
    render(<SlidesPreview text={"Slide one\nmeeting notes\n---\nSlide two"} searchQuery="meeting" />);
    const marks = document.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0]?.textContent).toBe("meeting");
  });

  it("reports total match count across all slides", async () => {
    const onMatchCountChange = vi.fn();
    render(
      <SlidesPreview
        text={"Slide alpha\ndata\n---\nSlide beta\ndata\n---\nSlide gamma\ndata"}
        searchQuery="data"
        onMatchCountChange={onMatchCountChange}
      />
    );
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(3);
    });
  });

  it("reports zero matches when query has no results", async () => {
    const onMatchCountChange = vi.fn();
    render(
      <SlidesPreview
        text={"Slide one\n---\nSlide two"}
        searchQuery="notfound"
        onMatchCountChange={onMatchCountChange}
      />
    );
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(0);
    });
  });
});
