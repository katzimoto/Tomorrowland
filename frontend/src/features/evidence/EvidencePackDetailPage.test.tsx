import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { EvidencePackDetailPage } from "./EvidencePackDetailPage";
import * as evidenceApi from "@/api/evidencePacks";
import type { EvidencePackDetail, EvidencePackItem } from "@/api/evidencePacks";
import { downloadTextFile } from "./exportEvidence";

vi.mock("@/api/evidencePacks");

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ packId: "pack-1" }),
  Link: ({
    children,
    to,
    params,
    target,
  }: {
    children: React.ReactNode;
    to: string;
    params?: Record<string, string>;
    target?: string;
  }) => {
    const href = params?.docId ? `/doc/${params.docId}` : to;
    return (
      <a href={href} target={target}>
        {children}
      </a>
    );
  },
}));

// Keep the real Markdown/JSON builders; only stub the browser download.
vi.mock("./exportEvidence", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportEvidence")>();
  return { ...actual, downloadTextFile: vi.fn() };
});

function makeItem(overrides: Partial<EvidencePackItem> = {}): EvidencePackItem {
  return {
    id: "item-1",
    evidence_pack_id: "pack-1",
    document_id: "doc-1",
    item_type: "citation",
    text_excerpt: "The contract terminates on December 31.",
    chunk_id: "chunk-7",
    citation_id: "cit-1",
    page_number: 3,
    section_heading: "Termination",
    translated_text: null,
    claim: null,
    created_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

function makePack(overrides: Partial<EvidencePackDetail> = {}): EvidencePackDetail {
  return {
    id: "pack-1",
    owner_user_id: "user-1",
    title: "Q3 Findings",
    description: "Key passages for the Q3 review.",
    source_scope: null,
    created_from: "chat",
    metadata: {},
    created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z",
    items: [makeItem()],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EvidencePackDetailPage", () => {
  it("renders pack metadata, items, and the open-document link (detail)", async () => {
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue(makePack());

    render(<EvidencePackDetailPage />);

    expect(await screen.findByText("Q3 Findings")).toBeInTheDocument();
    expect(screen.getByText("Key passages for the Q3 review.")).toBeInTheDocument();
    expect(screen.getByText("The contract terminates on December 31.")).toBeInTheDocument();
    expect(screen.getByText("p. 3 · Termination · chunk chunk-7")).toBeInTheDocument();
    const openLink = screen.getByRole("link", { name: /Open document/ });
    expect(openLink.getAttribute("href")).toBe("/doc/doc-1");
  });

  it("shows an empty state for a pack with no items (empty pack)", async () => {
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue(makePack({ items: [] }));

    render(<EvidencePackDetailPage />);

    expect(await screen.findByText("This evidence pack is empty")).toBeInTheDocument();
  });

  it("renders only the items the API returns, not ones for a removed document", async () => {
    // The backend filters out items whose document the caller can no longer
    // access, so the removed-document excerpt never reaches the client.
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue(
      makePack({ items: [makeItem({ document_id: "doc-1", text_excerpt: "Visible excerpt." })] }),
    );

    render(<EvidencePackDetailPage />);

    expect(await screen.findByText("Visible excerpt.")).toBeInTheDocument();
    expect(screen.queryByText(/removed-doc/)).not.toBeInTheDocument();
    expect(screen.queryByText("Hidden excerpt.")).not.toBeInTheDocument();
  });

  it("exports Markdown preserving citation/source metadata (Markdown export)", async () => {
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue(
      makePack({ items: [makeItem({ translated_text: "תרגום", claim: "A claim." })] }),
    );

    render(<EvidencePackDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Markdown/ }));

    expect(downloadTextFile).toHaveBeenCalledTimes(1);
    const [filename, content, mime] = vi.mocked(downloadTextFile).mock.calls[0];
    expect(filename).toBe("q3-findings.md");
    expect(mime).toBe("text/markdown");
    expect(content).toContain("# Q3 Findings");
    expect(content).toContain("Document: `doc-1`");
    expect(content).toContain("Citation: `cit-1`");
    expect(content).toContain("> _(translated)_ תרגום");
    expect(content).toContain("**Claim:** A claim.");
  });

  it("exports JSON preserving every item field (JSON export)", async () => {
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue(makePack());

    render(<EvidencePackDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: /JSON/ }));

    expect(downloadTextFile).toHaveBeenCalledTimes(1);
    const [filename, content, mime] = vi.mocked(downloadTextFile).mock.calls[0];
    expect(filename).toBe("q3-findings.json");
    expect(mime).toBe("application/json");
    const parsed = JSON.parse(content) as EvidencePackDetail;
    expect(parsed.items[0].citation_id).toBe("cit-1");
    expect(parsed.items[0].chunk_id).toBe("chunk-7");
  });

  it("removes an item after confirmation", async () => {
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue(makePack());
    vi.mocked(evidenceApi.removeEvidencePackItem).mockResolvedValue(undefined);

    render(<EvidencePackDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove item" }));
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));

    await waitFor(() => {
      expect(evidenceApi.removeEvidencePackItem).toHaveBeenCalledWith("pack-1", "item-1");
    });
  });
});
