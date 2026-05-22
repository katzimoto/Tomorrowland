import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { StarterQuestions } from "./StarterQuestions";

describe("StarterQuestions", () => {
  it("renders heading and question pills", () => {
    render(
      <StarterQuestions
        scopeType="all_accessible_documents"
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("Try asking")).toBeInTheDocument();
    expect(
      screen.getByText("Summarize my documents"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Find documents about contracts"),
    ).toBeInTheDocument();
  });

  it("calls onSelect with question text on click", () => {
    const onSelect = vi.fn();
    render(
      <StarterQuestions
        scopeType="all_accessible_documents"
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByText("What are the key topics?"));
    expect(onSelect).toHaveBeenCalledWith("What are the key topics?");
  });

  it("shows single_document questions for single_document scope", () => {
    render(
      <StarterQuestions
        scopeType="single_document"
        onSelect={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Summarize this document"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Who are the parties involved?"),
    ).toBeInTheDocument();
  });

  it("disables buttons when disabled prop is true", () => {
    render(
      <StarterQuestions
        scopeType="all_accessible_documents"
        onSelect={vi.fn()}
        disabled
      />,
    );
    const buttons = screen.getAllByRole("button");
    buttons.forEach((btn) => {
      expect(btn).toBeDisabled();
    });
  });

  it("has accessible group role", () => {
    render(
      <StarterQuestions
        scopeType="all_accessible_documents"
        onSelect={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("group", { name: "Suggested questions" }),
    ).toBeInTheDocument();
  });

  it("each pill has accessible label", () => {
    render(
      <StarterQuestions
        scopeType="all_accessible_documents"
        onSelect={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Ask: Summarize my documents" }),
    ).toBeInTheDocument();
  });
});
