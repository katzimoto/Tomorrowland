import { test, expect, vi } from "vitest";
import { screen, render } from "@/test/render";
import { ApiError } from "@/api/client";
import { AnnotationList } from "./AnnotationList";

vi.mock("@/api/auth", () => ({ getCurrentUser: vi.fn(() => Promise.resolve({ user_id: "u1", email: "a@example.com", display_name: "Ari", is_admin: false, groups: [] })) }));
vi.mock("@/api/annotations", () => ({ listAnnotations: vi.fn(() => Promise.reject(new ApiError(403, "Forbidden"))), createAnnotation: vi.fn() }));

test("renders annotation permission state without leaking document id", async () => {
  render(<AnnotationList docId="secret-doc" />);
  expect(await screen.findByText("Annotations unavailable")).toBeInTheDocument();
  expect(screen.queryByText("secret-doc")).not.toBeInTheDocument();
});
