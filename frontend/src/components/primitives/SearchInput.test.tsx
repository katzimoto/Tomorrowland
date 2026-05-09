import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchInput } from "./SearchInput";

describe("SearchInput", () => {
  it("renders search role", () => {
    render(<SearchInput value="" onChange={() => {}} />);
    expect(screen.getByRole("search")).toBeInTheDocument();
  });

  it("calls onChange when user types", () => {
    const onChange = vi.fn();
    render(<SearchInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "vendor" } });
    expect(onChange).toHaveBeenCalledWith("vendor");
  });

  it("shows clear button when value is non-empty", () => {
    render(<SearchInput value="query" onChange={() => {}} />);
    expect(screen.getByLabelText("Clear search")).toBeInTheDocument();
  });

  it("hides clear button when value is empty", () => {
    render(<SearchInput value="" onChange={() => {}} />);
    expect(screen.queryByLabelText("Clear search")).not.toBeInTheDocument();
  });

  it("calls onChange with empty string on clear", () => {
    const onChange = vi.fn();
    render(<SearchInput value="vendor" onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("Clear search"));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("calls onSubmit on Enter key", () => {
    const onSubmit = vi.fn();
    render(<SearchInput value="vendor" onChange={() => {}} onSubmit={onSubmit} />);
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
