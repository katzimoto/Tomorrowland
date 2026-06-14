import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { SaveToEvidencePackDialog, type EvidenceDraft } from "./SaveToEvidencePackDialog";
import * as evidenceApi from "@/api/evidencePacks";
import { ApiError } from "@/api/client";
import type {
  EvidencePack,
  EvidencePackDetail,
  EvidencePackItem,
} from "@/api/evidencePacks";

vi.mock("@/api/evidencePacks");

function makePack(overrides: Partial<EvidencePack> = {}): EvidencePack {
  return {
    id: "pack-1",
    owner_user_id: "user-1",
    title: "Q3 findings",
    description: null,
    source_scope: null,
    created_from: "chat",
    metadata: {},
    created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

function makeItem(overrides: Partial<EvidencePackItem> = {}): EvidencePackItem {
  return {
    id: "item-1",
    evidence_pack_id: "pack-1",
    document_id: "doc-1",
    item_type: "citation",
    text_excerpt: "excerpt",
    chunk_id: null,
    citation_id: "cit-1",
    page_number: null,
    section_heading: null,
    translated_text: null,
    claim: null,
    created_at: "2026-06-14T00:00:00Z",
    ...overrides,
  };
}

const DRAFT: EvidenceDraft = {
  document_id: "doc-1",
  item_type: "citation",
  text_excerpt: "The contract terminates on December 31.",
  citation_id: "cit-1",
  page_number: 3,
  section_heading: "Termination",
  title: "Contract.pdf",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SaveToEvidencePackDialog", () => {
  it("renders the item preview", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({ items: [] });

    render(
      <SaveToEvidencePackDialog open onClose={vi.fn()} draft={DRAFT} createdFrom="chat" />,
    );

    expect(await screen.findByText("Contract.pdf")).toBeInTheDocument();
    expect(screen.getByText(/December 31/)).toBeInTheDocument();
    expect(screen.getByText(/p\. 3/)).toBeInTheDocument();
  });

  it("creates a new pack then adds the item (create-new flow)", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({ items: [] });
    vi.mocked(evidenceApi.createEvidencePack).mockResolvedValue(
      makePack({ id: "pack-new", title: "Investigation" }),
    );
    vi.mocked(evidenceApi.addEvidencePackItem).mockResolvedValue(
      makeItem({ evidence_pack_id: "pack-new" }),
    );
    const onClose = vi.fn();

    render(
      <SaveToEvidencePackDialog open onClose={onClose} draft={DRAFT} createdFrom="chat" />,
    );

    // With no packs, the form defaults to create-new.
    const titleInput = await screen.findByLabelText("New pack title");
    fireEvent.change(titleInput, { target: { value: "Investigation" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(evidenceApi.createEvidencePack).toHaveBeenCalledWith({
        title: "Investigation",
        created_from: "chat",
      });
    });
    expect(evidenceApi.addEvidencePackItem).toHaveBeenCalledWith(
      "pack-new",
      expect.objectContaining({ document_id: "doc-1", citation_id: "cit-1" }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("adds the item to an existing pack (add-existing flow)", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({
      items: [makePack()],
    });
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue({
      ...makePack(),
      items: [],
    } as EvidencePackDetail);
    vi.mocked(evidenceApi.addEvidencePackItem).mockResolvedValue(makeItem());
    const onClose = vi.fn();

    render(
      <SaveToEvidencePackDialog open onClose={onClose} draft={DRAFT} createdFrom="chat" />,
    );

    // Existing pack is auto-selected once the list loads.
    await screen.findByLabelText("Choose evidence pack");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(evidenceApi.addEvidencePackItem).toHaveBeenCalledWith(
        "pack-1",
        expect.objectContaining({ document_id: "doc-1" }),
      );
    });
    expect(evidenceApi.createEvidencePack).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("warns and blocks saving when the item is already in the pack (duplicate)", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({
      items: [makePack()],
    });
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue({
      ...makePack(),
      items: [makeItem({ document_id: "doc-1", citation_id: "cit-1" })],
    } as EvidencePackDetail);

    render(
      <SaveToEvidencePackDialog open onClose={vi.fn()} draft={DRAFT} createdFrom="chat" />,
    );

    expect(
      await screen.findByText("This passage is already in the selected pack."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("reports a permission error clearly when the save fails (failed-save)", async () => {
    vi.mocked(evidenceApi.listEvidencePacks).mockResolvedValue({
      items: [makePack()],
    });
    vi.mocked(evidenceApi.getEvidencePack).mockResolvedValue({
      ...makePack(),
      items: [],
    } as EvidencePackDetail);
    vi.mocked(evidenceApi.addEvidencePackItem).mockRejectedValue(
      new ApiError(403, "Forbidden"),
    );

    render(
      <SaveToEvidencePackDialog open onClose={vi.fn()} draft={DRAFT} createdFrom="chat" />,
    );

    await screen.findByLabelText("Choose evidence pack");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(
        "You don't have permission to save evidence from this document.",
      ),
    ).toBeInTheDocument();
  });
});
