import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tabs } from "./Tabs";

const TABS = [
  { id: "summary", label: "Summary" },
  { id: "details", label: "Details" },
  { id: "notes", label: "Notes" },
];

describe("Tabs", () => {
  it("renders all tabs", () => {
    render(<Tabs tabs={TABS} active="summary" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Details" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Notes" })).toBeInTheDocument();
  });

  it("marks active tab as selected", () => {
    render(<Tabs tabs={TABS} active="details" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("calls onChange with tab id on click", () => {
    const onChange = vi.fn();
    render(<Tabs tabs={TABS} active="summary" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(onChange).toHaveBeenCalledWith("notes");
  });
});
