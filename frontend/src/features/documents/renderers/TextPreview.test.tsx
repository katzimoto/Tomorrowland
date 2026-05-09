import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { TextPreview } from "./TextPreview";

describe("TextPreview", () => {
  it("renders text content", () => {
    render(<TextPreview text="Hello world content" />);
    expect(screen.getByText("Hello world content")).toBeInTheDocument();
  });

  it("shows fallback when text is empty", () => {
    render(<TextPreview text="" />);
    expect(screen.getByText("No text content available.")).toBeInTheDocument();
  });
});
