import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

  it("table has accessible label", () => {
    render(<TablePreview text={"Name\tAge\nAlice\t30"} />);
    expect(screen.getByRole("table", { name: "Document table" })).toBeInTheDocument();
  });

  it("column headers have scope='col'", () => {
    const { container } = render(<TablePreview text={"Name\tAge\nAlice\t30"} />);
    const headers = container.querySelectorAll("th");
    headers.forEach((th) => {
      expect(th).toHaveAttribute("scope", "col");
  });
});


  it("uses ARIA table when virtualizing more than 1000 rows", () => {
    const header = "Col1\tCol2\n";
    const rows = Array.from({ length: 1001 }, (_, i) => `data${i}\tval${i}`).join("\n");
    render(<TablePreview text={header + rows} />);
    // With virtualization, uses div-based ARIA table instead of <table>
    expect(screen.getByRole("table", { name: "Document table" })).toBeInTheDocument();
    expect(document.querySelector("table")).not.toBeInTheDocument();
    // jsdom may not render virtual rows, but we didn't render 1001×2 cells
    const cells = document.querySelectorAll('[role="cell"]');
    expect(cells.length).toBeLessThan(1001 * 2);
  });

  describe("search", () => {
    it("highlights matching cells when searchQuery is provided", () => {
      render(<TablePreview text={"Name\tAge\nAlice\t30\nBob\t25"} searchQuery="Alice" />);
      const cells = document.querySelectorAll('[role="cell"]');
      const marks = cells[0]?.querySelectorAll("mark");
      expect(marks?.length).toBe(1);
      expect(marks?.[0]?.textContent).toBe("Alice");
    });

    it("reports match count via onMatchCountChange", async () => {
      const onMatchCountChange = vi.fn();
      render(
        <TablePreview
          text={"Name\tColor\nApple\tRed\nBerry\tBlue\nCarrot\tOrange"}
          searchQuery="e"
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
        <TablePreview
          text={"Name\tAge\nAlice\t30\nBob\t25"}
          searchQuery="notfound"
          onMatchCountChange={onMatchCountChange}
        />
      );
      await waitFor(() => {
        expect(onMatchCountChange).toHaveBeenCalledWith(0);
      });
    });
  });
});
