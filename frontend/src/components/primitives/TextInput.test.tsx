import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TextInput } from "./TextInput";

describe("TextInput", () => {
  it("renders with label", () => {
    render(<TextInput label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("shows error message and marks input invalid", () => {
    render(<TextInput label="Email" error="Invalid email" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid email");
  });

  it("shows hint when no error", () => {
    render(<TextInput label="Email" hint="We never share your email" />);
    expect(screen.getByText("We never share your email")).toBeInTheDocument();
  });

  it("calls onChange", () => {
    const handler = vi.fn();
    render(<TextInput label="Name" onChange={handler} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Alice" } });
    expect(handler).toHaveBeenCalled();
  });
});
