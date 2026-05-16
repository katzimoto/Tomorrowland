import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { VersionBanner } from "./VersionBanner";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, params }: { children: React.ReactNode; to: string; params?: Record<string, string> }) => (
    <a href={to.replace("$docId", params?.docId ?? "")}>{children}</a>
  ),
}));

describe("VersionBanner", () => {
  it("renders banner with link to latest document", () => {
    render(<VersionBanner latestDocumentId="latest-doc-abc" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/newer version/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view latest version/i });
    expect(link).toBeInTheDocument();
  });
});
