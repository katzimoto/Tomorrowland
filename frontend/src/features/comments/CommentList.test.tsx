import { test, expect, vi } from "vitest";
import { screen, render } from "@/test/render";
import { ApiError } from "@/api/client";
import { CommentList } from "./CommentList";

vi.mock("@/api/auth", () => ({ getCurrentUser: vi.fn(() => Promise.resolve({ user_id: "u1", email: "a@example.com", display_name: "Ari", is_admin: false, groups: [] })) }));
vi.mock("@/api/comments", () => ({ listComments: vi.fn(() => Promise.reject(new ApiError(403, "Forbidden"))), createComment: vi.fn() }));

test("renders permission state without a document title", async () => {
  render(<CommentList docId="secret-doc" />);
  expect(await screen.findByText("Comments unavailable")).toBeInTheDocument();
  expect(screen.queryByText("secret-doc")).not.toBeInTheDocument();
});
