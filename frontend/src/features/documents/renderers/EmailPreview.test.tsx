import { describe, it, expect, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { EmailPreview } from "./EmailPreview";

describe("EmailPreview search", () => {
  const sampleMetadata = { from: "alice@example.com", to: "bob@example.com", subject: "Hello" };

  it("highlights matches in email body when searchQuery is provided", () => {
    render(
      <EmailPreview
        text="Hello world, this is a test message."
        metadata={sampleMetadata}
        searchQuery="test"
      />
    );
    const marks = document.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0]?.textContent).toBe("test");
  });

  it("reports match count via onMatchCountChange", async () => {
    const onMatchCountChange = vi.fn();
    render(
      <EmailPreview
        text="foo bar foo baz foo"
        metadata={sampleMetadata}
        searchQuery="foo"
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
      <EmailPreview
        text="hello world"
        metadata={sampleMetadata}
        searchQuery="notfound"
        onMatchCountChange={onMatchCountChange}
      />
    );
    await waitFor(() => {
      expect(onMatchCountChange).toHaveBeenCalledWith(0);
    });
  });
});
