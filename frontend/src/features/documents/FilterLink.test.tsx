import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, search, ...props }: Record<string, unknown>) => {
    const sp = search as Record<string, string>;
    const params = new URLSearchParams(sp).toString();
    const href = `${to as string}?${params}`;
    return (
      <a href={href} {...props} aria-label="mock link">{children as React.ReactNode}</a>
    );
  },
  useSearch: () => ({}),
}));

import { FilterLink } from "./FilterLink";

describe("FilterLink", () => {
  it("renders source field as link to search with source param", () => {
    render(<FilterLink field="source" value="nifi" />);
    const link = screen.getByRole("link", { name: /search for documents/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("source=nifi"));
    expect(link).toHaveTextContent("nifi");
  });

  it("renders tags field as link with tags param", () => {
    render(<FilterLink field="tags" value="contract" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", expect.stringContaining("tags=contract"));
  });

  it("renders file_type field as link", () => {
    render(<FilterLink field="file_type" value="application/pdf" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", expect.stringContaining("file_type=application"));
  });

  it("renders file_extension field as link", () => {
    render(<FilterLink field="file_extension" value="pdf" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", expect.stringContaining("file_extension=pdf"));
  });

  it("renders children instead of value when provided", () => {
    render(<FilterLink field="tags" value="hidden"><span data-testid="child">Custom</span></FilterLink>);
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
  });

  it("returns plain text for unsupported field", () => {
    const { container } = render(<FilterLink field="unknown" value="x" />);
    expect(container.querySelector("a")).not.toBeInTheDocument();
    expect(container.textContent).toContain("x");
  });
});
