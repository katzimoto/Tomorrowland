import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { RendererStatusBadge } from "./RendererStatusBadge";
import type { PreviewManifest } from "@/api/preview";
import * as previewApi from "@/api/preview";
import * as authApi from "@/api/auth";

vi.mock("@/api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof previewApi>()),
  usePreviewManifest: vi.fn(),
  rerenderPreview: vi.fn(),
}));

vi.mock("@/api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof authApi>()),
  getCurrentUser: vi.fn(),
}));

const mockedManifest = vi.mocked(previewApi.usePreviewManifest);
const mockedRerender = vi.mocked(previewApi.rerenderPreview);
const mockedUser = vi.mocked(authApi.getCurrentUser);

function manifest(over: Partial<PreviewManifest>): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: "sha256:abc",
    kind: "email",
    renderer: "email",
    status: "ready",
    error: null,
    generated_at: null,
    retry_after_ms: null,
    navigation: { unit: "none", count: 0, items: [] },
    artifacts: [],
    email: null,
    office: null,
    evidence: { supports_text_search: true, anchor_unit: "body", regions_available: false },
    ...over,
  };
}

function manifestResult(data: PreviewManifest | undefined) {
  return { data, isLoading: false, isError: false } as ReturnType<
    typeof previewApi.usePreviewManifest
  >;
}

beforeEach(() => {
  mockedManifest.mockReset();
  mockedRerender.mockReset();
  mockedUser.mockReset();
  mockedUser.mockResolvedValue({
    user_id: "u1",
    email: "a@example.com",
    display_name: "Admin",
    is_admin: true,
    groups: [],
  });
});

describe("RendererStatusBadge", () => {
  it("shows renderer + status for an admin on a worker-rendered doc", async () => {
    mockedManifest.mockReturnValue(manifestResult(manifest({ renderer: "libreoffice_pdf" })));
    render(<RendererStatusBadge docId="doc-1" />);
    expect(await screen.findByText("libreoffice_pdf")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("surfaces the failure category for admins", async () => {
    mockedManifest.mockReturnValue(
      manifestResult(
        manifest({ status: "failed", error: { category: "render_timeout", detail: "120s" } }),
      ),
    );
    render(<RendererStatusBadge docId="doc-1" />);
    expect(await screen.findByText(/render_timeout/)).toBeInTheDocument();
  });

  it("calls the rerender endpoint when clicked", async () => {
    mockedManifest.mockReturnValue(manifestResult(manifest({ status: "ready" })));
    mockedRerender.mockResolvedValue({ status: "pending" });
    render(<RendererStatusBadge docId="doc-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Re-render" }));
    await waitFor(() => expect(mockedRerender).toHaveBeenCalledWith("doc-1"));
  });

  it("renders nothing for non-admins", async () => {
    mockedUser.mockResolvedValue({
      user_id: "u2",
      email: "b@example.com",
      display_name: "User",
      is_admin: false,
      groups: [],
    });
    mockedManifest.mockReturnValue(manifestResult(manifest({})));
    const { container } = render(<RendererStatusBadge docId="doc-1" />);
    await waitFor(() => expect(mockedUser).toHaveBeenCalled());
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("renders nothing for ready-immediate (non-worker) renderers", async () => {
    mockedManifest.mockReturnValue(manifestResult(manifest({ renderer: "text" })));
    const { container } = render(<RendererStatusBadge docId="doc-1" />);
    await waitFor(() => expect(mockedUser).toHaveBeenCalled());
    expect(container.querySelector('[role="status"]')).toBeNull();
  });
});
