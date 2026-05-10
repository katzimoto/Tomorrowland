import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { HtmlPreview } from "./HtmlPreview";

describe("HtmlPreview", () => {
  it("renders sanitized HTML content", () => {
    render(<HtmlPreview html="<p>Safe content</p>" />);
    expect(screen.getByText("Safe content")).toBeInTheDocument();
  });

  it("strips script tags", () => {
    render(<HtmlPreview html="<p>Safe</p><script>alert('xss')</script>" />);
    expect(screen.queryByText("alert('xss')")).not.toBeInTheDocument();
    expect(screen.getByText("Safe")).toBeInTheDocument();
  });

  it("strips style tags", () => {
    const { container } = render(<HtmlPreview html="<p>Text</p><style>body{color:red}</style>" />);
    expect(container.querySelector("style")).toBeNull();
  });
});
