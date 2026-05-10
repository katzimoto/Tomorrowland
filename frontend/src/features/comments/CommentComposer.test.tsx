import { test, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, render } from "@/test/render";
import { CommentComposer } from "./CommentComposer";

vi.mock("@/api/comments", () => ({ createComment: vi.fn(() => Promise.resolve({ id: "c1" })) }));

test("enables submit after typing a draft", async () => {
  const user = userEvent.setup();
  render(<CommentComposer docId="d1" />);
  const button = screen.getByRole("button", { name: "Post comment" });
  expect(button).toBeDisabled();
  await user.type(screen.getByLabelText("Add a comment"), "Looks useful 😀");
  expect(button).toBeEnabled();
});
