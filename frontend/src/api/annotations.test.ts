import { beforeEach, expect, test, vi } from "vitest";
import { api } from "./client";
import { createAnnotation, listAnnotations, updateAnnotation } from "./annotations";

vi.mock("./client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const put = vi.mocked(api.put);

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
});

test("maps the backend annotations envelope and privacy fields", async () => {
  get.mockResolvedValueOnce({
    document_id: "d1",
    annotations: [{ id: "a1", user_id: "u1", user_display_name: "Ari", text: "Shared note", position: { page: 2 }, is_private: false, created_at: "2026-05-01T10:00:00Z", updated_at: "2026-05-01T11:00:00Z" }],
  });

  await expect(listAnnotations("d1")).resolves.toEqual([
    { id: "a1", document_id: "d1", author_id: "u1", author_name: "Ari", body: "Shared note", position: { page: 2 }, shared: true, created_at: "2026-05-01T10:00:00Z", updated_at: "2026-05-01T11:00:00Z", can_modify: false },
  ]);
});

test("maps create and update writes to backend annotation payloads", async () => {
  const response = { id: "a1", document_id: "d1", user_id: "u1", user_display_name: "Ari", text: "Private note", position: { page: 1 }, is_private: true, created_at: "2026-05-01T10:00:00Z", updated_at: "2026-05-01T10:00:00Z" };
  post.mockResolvedValueOnce(response);
  put.mockResolvedValueOnce(response);

  await createAnnotation("d1", { body: "Private note", shared: false, position: { page: 1 } });
  await updateAnnotation("a1", { body: "Shared note", shared: true, position: { page: 3 } });

  expect(post).toHaveBeenCalledWith("/documents/d1/annotations", { text: "Private note", is_private: true, position: { page: 1 } });
  expect(put).toHaveBeenCalledWith("/annotations/a1", { text: "Shared note", is_private: false, position: { page: 3 } });
});
