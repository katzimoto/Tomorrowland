import { test, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, render, waitFor } from "@/test/render";
import { CommentComposer } from "./CommentComposer";

const mocks = vi.hoisted(() => ({ createComment: vi.fn() }));
vi.mock("@/api/comments", () => ({ createComment: mocks.createComment }));

beforeEach(() => {
  mocks.createComment.mockReset();
  mocks.createComment.mockResolvedValue({ id: "c1" });
});

test("enables submit after typing a draft", async () => {
  const user = userEvent.setup();
  render(<CommentComposer docId="d1" />);
  const button = screen.getByRole("button", { name: "Post comment" });
  expect(button).toBeDisabled();
  await user.type(screen.getByLabelText("Add a comment"), "Looks useful 😀");
  expect(button).toBeEnabled();
});

test("Enter submits the comment", async () => {
  const user = userEvent.setup();
  render(<CommentComposer docId="d1" />);
  await user.type(screen.getByLabelText("Add a comment"), "quick note");
  await user.keyboard("{Enter}");
  await waitFor(() => expect(mocks.createComment).toHaveBeenCalledWith("d1", "quick note"));
});

test("Shift+Enter inserts a newline instead of submitting", async () => {
  const user = userEvent.setup();
  render(<CommentComposer docId="d1" />);
  await user.type(screen.getByLabelText("Add a comment"), "line one");
  await user.keyboard("{Shift>}{Enter}{/Shift}");
  // textarea value contains a newline; API is NOT called
  expect(screen.getByLabelText("Add a comment")).toHaveValue("line one\n");
  expect(mocks.createComment).not.toHaveBeenCalled();
});
