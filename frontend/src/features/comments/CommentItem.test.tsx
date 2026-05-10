import { test, expect } from "vitest";
import { screen } from "@/test/render";
import { render } from "@/test/render";
import { CommentItem } from "./CommentItem";
import type { Comment } from "@/api/comments";

const comment: Comment = { id: "c1", doc_id: "d1", author_id: "u1", author_name: "Ari", body: "hello", created_at: "2026-05-10T00:00:00Z" };

test("shows edit actions for the creator", () => {
  render(<CommentItem docId="d1" comment={comment} currentUser={{ user_id: "u1", email: "a@example.com", display_name: "Ari", is_admin: false, groups: [] }} />);
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
});

test("keeps other readers in read-only view", () => {
  render(<CommentItem docId="d1" comment={comment} currentUser={{ user_id: "u2", email: "b@example.com", display_name: "Bea", is_admin: false, groups: [] }} />);
  expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
});
