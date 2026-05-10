import { test, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, render } from "@/test/render";
import { AnnotationEditor } from "./AnnotationEditor";

vi.mock("@/api/annotations", () => ({ createAnnotation: vi.fn(() => Promise.resolve({ id: "a1" })), updateAnnotation: vi.fn() }));

test("supports shared annotation toggle", async () => {
  const user = userEvent.setup();
  render(<AnnotationEditor docId="d1" />);
  await user.type(screen.getByLabelText("New annotation"), "private note");
  await user.click(screen.getByLabelText("Share with readers who can access this document"));
  expect(screen.getByLabelText("Share with readers who can access this document")).toBeChecked();
});
