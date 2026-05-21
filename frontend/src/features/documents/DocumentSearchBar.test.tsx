import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DocumentSearchBar } from "./DocumentSearchBar";

const baseProps = {
  query: "",
  matchCount: 0,
  activeIndex: 0,
  onQueryChange: vi.fn(),
  onNext: vi.fn(),
  onPrev: vi.fn(),
  onClose: vi.fn(),
};

describe("DocumentSearchBar", () => {
  it("renders the search input with correct aria-label", () => {
    render(<DocumentSearchBar {...baseProps} />);
    expect(screen.getByRole("searchbox", { name: "Search within document" })).toBeInTheDocument();
  });

  it("shows 'No results' when query is set but matchCount is 0", () => {
    render(<DocumentSearchBar {...baseProps} query="xyz" matchCount={0} />);
    expect(screen.getByText("No results")).toBeInTheDocument();
  });

  it("shows empty counter when query is empty and matchCount is 0", () => {
    render(<DocumentSearchBar {...baseProps} query="" matchCount={0} />);
    expect(screen.queryByText("No results")).not.toBeInTheDocument();
    expect(screen.queryByText(/of/)).not.toBeInTheDocument();
  });

  it("shows '1 of 5' when matchCount=5 and activeIndex=0", () => {
    render(<DocumentSearchBar {...baseProps} query="test" matchCount={5} activeIndex={0} />);
    expect(screen.getByText("1 of 5")).toBeInTheDocument();
  });

  it("shows '3 of 5' when activeIndex=2", () => {
    render(<DocumentSearchBar {...baseProps} query="test" matchCount={5} activeIndex={2} />);
    expect(screen.getByText("3 of 5")).toBeInTheDocument();
  });

  it("calls onQueryChange when input changes", () => {
    const onQueryChange = vi.fn();
    render(<DocumentSearchBar {...baseProps} onQueryChange={onQueryChange} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "hello" } });
    expect(onQueryChange).toHaveBeenCalledWith("hello");
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<DocumentSearchBar {...baseProps} onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onNext when Enter is pressed", () => {
    const onNext = vi.fn();
    render(<DocumentSearchBar {...baseProps} matchCount={3} onNext={onNext} />);
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Enter" });
    expect(onNext).toHaveBeenCalled();
  });

  it("calls onPrev when Shift+Enter is pressed", () => {
    const onPrev = vi.fn();
    render(<DocumentSearchBar {...baseProps} matchCount={3} onPrev={onPrev} />);
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Enter", shiftKey: true });
    expect(onPrev).toHaveBeenCalled();
  });

  it("next/prev buttons are disabled when matchCount is 0", () => {
    render(<DocumentSearchBar {...baseProps} matchCount={0} />);
    expect(screen.getByRole("button", { name: "Next match" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous match" })).toBeDisabled();
  });

  it("next/prev buttons are enabled when matchCount > 0", () => {
    render(<DocumentSearchBar {...baseProps} matchCount={3} />);
    expect(screen.getByRole("button", { name: "Next match" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous match" })).not.toBeDisabled();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    render(<DocumentSearchBar {...baseProps} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Close search" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("counter is an aria-live polite region", () => {
    render(<DocumentSearchBar {...baseProps} query="test" matchCount={3} activeIndex={0} />);
    const counter = screen.getByText("1 of 3");
    expect(counter).toHaveAttribute("aria-live", "polite");
  });
});
