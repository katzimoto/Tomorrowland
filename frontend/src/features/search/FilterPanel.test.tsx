import { describe, it, expect, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { render } from "@/test/render";
import { FilterPanel } from "./FilterPanel";
import type { SearchFilters } from "@/api/search";

describe("FilterPanel — include older versions", () => {
  it("renders 'Include older versions' checkbox unchecked by default", () => {
    render(<FilterPanel filters={{}} onChange={vi.fn()} />);
    const cb = screen.getByRole("checkbox", { name: /include older versions/i });
    expect(cb).not.toBeChecked();
  });

  it("calls onChange with include_older_versions=true when checked", () => {
    const onChange = vi.fn();
    render(<FilterPanel filters={{}} onChange={onChange} />);
    const cb = screen.getByRole("checkbox", { name: /include older versions/i });
    fireEvent.click(cb);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ include_older_versions: true }),
    );
  });

  it("calls onChange without include_older_versions when unchecked", () => {
    const onChange = vi.fn();
    const filters: SearchFilters = { include_older_versions: true };
    render(<FilterPanel filters={filters} onChange={onChange} />);
    const cb = screen.getByRole("checkbox", { name: /include older versions/i });
    expect(cb).toBeChecked();
    fireEvent.click(cb);
    // false → onChange receives undefined (treated as false)
    const call = onChange.mock.calls[0][0] as SearchFilters;
    expect(call.include_older_versions == null || call.include_older_versions === false).toBe(true);
  });

  it("shows clear all button when include_older_versions is true", () => {
    render(<FilterPanel filters={{ include_older_versions: true }} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /clear all/i })).toBeInTheDocument();
  });
});
