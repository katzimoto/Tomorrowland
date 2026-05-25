import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { HtmlPreview } from "./HtmlPreview";

describe("HtmlPreview", () => {
  it("renders an iframe", () => {
    const { container } = render(<HtmlPreview html="<p>Hello</p>" />);
    expect(container.querySelector("iframe")).not.toBeNull();
  });

  it("passes html as srcDoc with dark-mode override prepended", () => {
    const html = "<p>Document content</p>";
    const { container } = render(<HtmlPreview html={html} />);
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    const srcdoc = iframe.getAttribute("srcdoc") ?? "";
    // The dark-mode stylesheet is injected before the document content
    expect(srcdoc).toContain("<style>");
    expect(srcdoc).toContain(html);
  });

  it("sandboxes the iframe without allow-scripts", () => {
    const { container } = render(<HtmlPreview html="<p>test</p>" />);
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    const sandbox = iframe.getAttribute("sandbox") ?? "";
    expect(sandbox).toContain("allow-same-origin");
    expect(sandbox).not.toContain("allow-scripts");
  });

  it("has an accessible title", () => {
    render(<HtmlPreview html="<p>test</p>" />);
    expect(screen.getByTitle("HTML document preview")).toBeInTheDocument();
  });
});
