import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { VersionBadge } from "./VersionBadge";

describe("VersionBadge", () => {
  it("shows version number for latest version", () => {
    render(<VersionBadge versionNumber={3} isLatest={true} />);
    expect(screen.getByText(/Version 3/)).toBeInTheDocument();
    expect(screen.getByText(/Latest/)).toBeInTheDocument();
  });

  it("shows version number for older version without Latest label", () => {
    render(<VersionBadge versionNumber={1} isLatest={false} />);
    expect(screen.getByText(/Version 1/)).toBeInTheDocument();
    expect(screen.queryByText(/Latest/)).not.toBeInTheDocument();
  });
});
