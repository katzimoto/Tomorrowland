import { test, expect } from "vitest";
import { screen, render } from "@/test/render";
import { AnnotationItem } from "./AnnotationItem";
import type { Annotation } from "@/api/annotations";

const annotation: Annotation = { id: "a1", doc_id: "d1", author_id: "u1", author_name: "Ari", body: "note", position: { page: 2 }, shared: true, created_at: "2026-05-10T00:00:00Z" };

test("shows shared label and position evidence", () => {
  render(<AnnotationItem docId="d1" annotation={annotation} currentUser={{ user_id: "u2", email: "b@example.com", display_name: "Bea", is_admin: false, groups: [] }} />);
  expect(screen.getByText("Shared with readers")).toBeInTheDocument();
  expect(screen.getByText("Page 2")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
});
