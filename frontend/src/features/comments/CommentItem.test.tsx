import { test, expect } from "vitest";
import { screen } from "@/test/render";
import { render } from "@/test/render";
import { CommentItem } from "./CommentItem";
import type { Comment } from "@/api/comments";

const comment: Comment = {
  id: "c1",
  doc_id: "d1",
  author_id: "u1",
  author_name: "Ari",
  body: "hello",
  created_at: "2026-05-10T00:00:00Z",
  can_edit: false,
  can_delete: false,
};

test("shows edit actions for the creator", () => {
  render(
    <CommentItem
      docId="d1"
      comment={{ ...comment, can_edit: true, can_delete: true }}
      currentUser={{ user_id: "u1", email: "a@example.com", display_name: "Ari", is_admin: false, groups: [] }}
    />,
  );
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
});

test("keeps other readers in read-only view", () => {
  render(
    <CommentItem
      docId="d1"
      comment={comment}
      currentUser={{ user_id: "u2", email: "b@example.com", display_name: "Bea", is_admin: false, groups: [] }}
    />,
  );
  expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
});

test("shows both edit and delete when can_edit and can_delete are true", () => {
  render(
    <CommentItem
      docId="d1"
      comment={{ ...comment, can_edit: true, can_delete: true }}
      currentUser={{ user_id: "u1", email: "a@example.com", display_name: "Ari", is_admin: false, groups: [] }}
    />,
  );
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
});

test("hides both controls when can_edit and can_delete are false even for owner", () => {
  render(
    <CommentItem
      docId="d1"
      comment={comment}
      currentUser={{ user_id: "u1", email: "a@example.com", display_name: "Ari", is_admin: false, groups: [] }}
    />,
  );
  expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
});
