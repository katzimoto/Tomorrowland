import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { QuestionInput } from "./QuestionInput";

describe("QuestionInput", () => {
  it("renders textarea", () => {
    render(<QuestionInput value="" onChange={vi.fn()} onSubmit={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "Question" })).toBeInTheDocument();
  });

  it("calls onChange when typing", () => {
    const onChange = vi.fn();
    render(<QuestionInput value="" onChange={onChange} onSubmit={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "What is risk?" } });
    expect(onChange).toHaveBeenCalledWith("What is risk?");
  });

  it("calls onSubmit on Enter without shift", () => {
    const onSubmit = vi.fn();
    render(<QuestionInput value="What is risk?" onChange={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: false });
    expect(onSubmit).toHaveBeenCalled();
  });

  it("does not submit on Shift+Enter", () => {
    const onSubmit = vi.fn();
    render(<QuestionInput value="What is risk?" onChange={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not submit when disabled", () => {
    const onSubmit = vi.fn();
    render(<QuestionInput value="What is risk?" onChange={vi.fn()} onSubmit={onSubmit} disabled />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: false });
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
