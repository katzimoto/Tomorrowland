import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { HtmlPreview } from "./HtmlPreview";

describe("HtmlPreview", () => {
  it("renders an iframe", () => {
    const { container } = render(<HtmlPreview html="<p>Hello</p>" />);
    expect(container.querySelector("iframe")).not.toBeNull();
  });

  it("passes html as srcDoc", () => {
    const html = "<p>Document content</p>";
    const { container } = render(<HtmlPreview html={html} />);
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    expect(iframe.getAttribute("srcdoc")).toBe(html);
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

  it("passes script content through srcdoc (not stripped)", () => {
    const malicious = '<script>window.__xss=1</script><p>safe</p>';
    const { container } = render(<HtmlPreview html={malicious} />);
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    const srcdoc = iframe.getAttribute("srcdoc") ?? "";
    expect(srcdoc).toContain("<script>");
    expect(srcdoc).toContain("window.__xss");
    expect(srcdoc).toContain("<p>safe</p>");
  });

  it("prevents all script-related sandbox tokens", () => {
    const { container } = render(<HtmlPreview html='<script>alert(1)</script>' />);
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    const sandbox = iframe.getAttribute("sandbox") ?? "";
    expect(sandbox).not.toContain("allow-scripts");
    expect(sandbox).not.toContain("allow-popups");
    expect(sandbox).not.toContain("allow-top-navigation");
    expect(sandbox).not.toContain("allow-pointer-lock");
  });
});
