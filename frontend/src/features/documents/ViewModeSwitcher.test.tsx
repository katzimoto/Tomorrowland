import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ViewModeSwitcher } from "./ViewModeSwitcher";
import type { ViewMode } from "./ViewModeSwitcher";

describe("ViewModeSwitcher", () => {
  it("renders nothing when only one mode is available", () => {
    const { container } = render(
      <ViewModeSwitcher
        availableModes={["original"]}
        activeMode="original"
        onModeChange={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders all available modes as buttons", () => {
    render(
      <ViewModeSwitcher
        availableModes={["original", "extracted", "translation"]}
        activeMode="original"
        onModeChange={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Original" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extracted" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Translation" })).toBeInTheDocument();
  });

  it("marks the active mode button as pressed", () => {
    render(
      <ViewModeSwitcher
        availableModes={["original", "translation"]}
        activeMode="translation"
        onModeChange={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Translation" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Original" })).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onModeChange with the clicked mode", () => {
    const onModeChange = vi.fn();
    render(
      <ViewModeSwitcher
        availableModes={["original", "extracted", "translation"]}
        activeMode="original"
        onModeChange={onModeChange}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Extracted" }));
    expect(onModeChange).toHaveBeenCalledWith("extracted" satisfies ViewMode);
  });

  it("hides switcher when exactly one mode is in the list", () => {
    const { container } = render(
      <ViewModeSwitcher
        availableModes={["translation"]}
        activeMode="translation"
        onModeChange={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the group with accessible label", () => {
    render(
      <ViewModeSwitcher
        availableModes={["original", "translation"]}
        activeMode="original"
        onModeChange={vi.fn()}
      />
    );
    expect(screen.getByRole("group", { name: "View mode" })).toBeInTheDocument();
  });
});
