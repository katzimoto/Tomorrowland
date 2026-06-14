import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { EvidencePacksPage } from "./EvidencePacksPage";
import * as evidenceApi from "@/api/evidencePacks";
import type { EvidencePack } from "@/api/evidencePacks";

vi.mock("@/api/evidencePacks");

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    params,
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, string>;
  }) => <a href={params?.packId ? `/evidence/${params.packId}` : to}>{children}</a>,
}));

function makePack(overrides: Partial<EvidencePack> = {}): EvidencePack {
  return {
    id: "pack-1",
    owner_user_id: "user-1",
    title: "Q3 Findings",
    description: "Key passages.",
    source_scope: null,
    created_from: "chat",
    metadata: {},
    created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EvidencePacksPage", () => {
  it("lists packs with links to their detail pages", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({ items: [makePack()] });

    render(<EvidencePacksPage />);

    const link = await screen.findByRole("link", { name: /Q3 Findings/ });
    expect(link.getAttribute("href")).toBe("/evidence/pack-1");
  });

  it("shows an empty state when there are no packs", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({ items: [] });

    render(<EvidencePacksPage />);

    expect(await screen.findByText("No evidence packs yet")).toBeInTheDocument();
  });
});
