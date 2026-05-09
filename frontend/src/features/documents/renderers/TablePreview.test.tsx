import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { TablePreview } from "./TablePreview";

describe("TablePreview", () => {
  it("renders table with header and rows", () => {
    render(<TablePreview text={"Name\tAge\nAlice\t30\nBob\t25"} />);
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Alice" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "30" })).toBeInTheDocument();
  });

  it("shows fallback for empty text", () => {
    render(<TablePreview text="" />);
    expect(screen.getByText("No table data available.")).toBeInTheDocument();
  });
});
