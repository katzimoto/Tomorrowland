import { test, expect } from "vitest";
import { screen, render } from "@/test/render";
import { PrivacyLabel } from "./PrivacyLabel";

test("labels private and shared annotations", () => {
  const { rerender } = render(<PrivacyLabel shared={false} />);
  expect(screen.getByText("Private note")).toBeInTheDocument();
  rerender(<PrivacyLabel shared />);
  expect(screen.getByText("Shared with readers")).toBeInTheDocument();
});
