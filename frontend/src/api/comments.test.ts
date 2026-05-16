import { beforeEach, expect, test, vi } from "vitest";
import { api } from "./client";
import { listComments } from "./comments";

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

beforeEach(() => {
  get.mockReset();
});

test("maps the backend comments envelope and query params", async () => {
  get.mockResolvedValueOnce({
    doc_id: "d1",
    comments: [{ id: "c1", author_id: "u1", author_display_name: "Ari", body: "Hello", created_at: "2026-05-01T10:00:00Z", edited_at: "2026-05-01T11:00:00Z", edited_by_id: "u1", deleted_at: null }],
    total: 1,
    skip: 5,
    limit: 10,
  });

  await expect(listComments("d1", { limit: 10, offset: 5, sort: "-created_at" })).resolves.toEqual([
    { id: "c1", doc_id: "d1", author_id: "u1", author_name: "Ari", author: undefined, body: "Hello", created_at: "2026-05-01T10:00:00Z", updated_at: "2026-05-01T11:00:00Z", can_edit: false, can_delete: false },
  ]);
  expect(get).toHaveBeenCalledWith("/documents/d1/comments?limit=10&skip=5&sort=newest");
});

test("maps ascending frontend sort to backend oldest", async () => {
  get.mockResolvedValueOnce({ doc_id: "d1", comments: [], total: 0, skip: 0, limit: 50 });

  await listComments("d1", { sort: "created_at" });

  expect(get).toHaveBeenCalledWith("/documents/d1/comments?sort=oldest");
});
