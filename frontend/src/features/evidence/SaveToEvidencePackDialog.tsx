import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus } from "lucide-react";
import { ApiError } from "@/api/client";
import {
  addEvidencePackItem,
  createEvidencePack,
  getEvidencePack,
  listEvidencePacks,
  type EvidencePackCreatedFrom,
  type EvidencePackItem,
  type EvidencePackItemInput,
} from "@/api/evidencePacks";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { TextInput } from "@/components/primitives/TextInput";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./SaveToEvidencePackDialog.module.css";

/** A single item the user wants to save, plus a display title for the preview. */
export interface EvidenceDraft extends EvidencePackItemInput {
  /** Document title shown in the preview; not persisted as item data. */
  title?: string | null;
}

interface SaveToEvidencePackDialogProps {
  open: boolean;
  onClose: () => void;
  draft: EvidenceDraft | null;
  createdFrom: EvidencePackCreatedFrom;
}

type Mode = "existing" | "new";

/** Two items refer to the same evidence when their document and anchor match. */
function isSameAnchor(item: EvidencePackItem, draft: EvidenceDraft): boolean {
  if (item.document_id !== draft.document_id) return false;
  if (draft.citation_id) return item.citation_id === draft.citation_id;
  if (draft.chunk_id) return item.chunk_id === draft.chunk_id;
  return item.text_excerpt === draft.text_excerpt;
}

function saveErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "You don't have permission to save evidence from this document.";
    }
    if (error.status === 404) {
      return "This document is no longer available.";
    }
    return error.message || "Failed to save to evidence pack.";
  }
  return "Failed to save to evidence pack.";
}

function toItemInput(draft: EvidenceDraft): EvidencePackItemInput {
  return {
    document_id: draft.document_id,
    item_type: draft.item_type,
    text_excerpt: draft.text_excerpt,
    chunk_id: draft.chunk_id ?? null,
    citation_id: draft.citation_id ?? null,
    page_number: draft.page_number ?? null,
    section_heading: draft.section_heading ?? null,
    translated_text: draft.translated_text ?? null,
    claim: draft.claim ?? null,
  };
}

/**
 * Form body. Mounted by {@link Dialog} only while the dialog is open, so its
 * state resets naturally on each open without effects.
 */
function SaveEvidenceForm({
  draft,
  createdFrom,
  onClose,
}: {
  draft: EvidenceDraft | null;
  createdFrom: EvidencePackCreatedFrom;
  onClose: () => void;
}) {
  const { show: showToast } = useToast();
  const queryClient = useQueryClient();

  // `null` means "use the data-driven default"; a value means the user chose.
  const [modeOverride, setModeOverride] = useState<Mode | null>(null);
  const [pickedPackId, setPickedPackId] = useState("");
  const [title, setTitle] = useState("");

  const packsQuery = useQuery({ queryKey: ["evidence-packs"], queryFn: listEvidencePacks });
  const packs = packsQuery.data?.items ?? [];

  // Prefer adding to an existing pack when the user has any; derived, not stored.
  const mode: Mode = modeOverride ?? (packs.length > 0 ? "existing" : "new");
  const selectedPackId = pickedPackId || packs[0]?.id || "";

  const detailQuery = useQuery({
    queryKey: ["evidence-pack", selectedPackId],
    queryFn: () => getEvidencePack(selectedPackId),
    enabled: mode === "existing" && !!selectedPackId,
  });

  const isDuplicate =
    mode === "existing" &&
    !!draft &&
    (detailQuery.data?.items ?? []).some((item) => isSameAnchor(item, draft));

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error("No evidence to save.");
      let packId = selectedPackId;
      if (mode === "new") {
        const pack = await createEvidencePack({ title: title.trim(), created_from: createdFrom });
        packId = pack.id;
      }
      return addEvidencePackItem(packId, toItemInput(draft));
    },
    onSuccess: (item) => {
      void queryClient.invalidateQueries({ queryKey: ["evidence-packs"] });
      void queryClient.invalidateQueries({ queryKey: ["evidence-pack", item.evidence_pack_id] });
      showToast("success", "Saved to evidence pack.");
      onClose();
    },
  });

  const canSave =
    !!draft &&
    !isDuplicate &&
    !saveMutation.isPending &&
    (mode === "new" ? title.trim().length > 0 : !!selectedPackId);

  const location = draft
    ? [draft.page_number != null ? `p. ${draft.page_number}` : null, draft.section_heading || null]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <div className={styles.body}>
      {draft && (
        <div className={styles.preview}>
          {draft.title && <span className={styles.previewTitle}>{draft.title}</span>}
          {location && <span className={styles.previewLocation}>{location}</span>}
          {draft.text_excerpt && <p className={styles.previewExcerpt}>{draft.text_excerpt}</p>}
        </div>
      )}

      <fieldset className={styles.modeGroup} disabled={saveMutation.isPending}>
        <legend className={styles.legend}>Destination</legend>
        {packs.length > 0 && (
          <label className={styles.modeOption}>
            <input
              type="radio"
              name="evidence-pack-mode"
              checked={mode === "existing"}
              onChange={() => setModeOverride("existing")}
            />
            Add to existing pack
          </label>
        )}
        {mode === "existing" && packs.length > 0 && (
          <select
            className={styles.select}
            aria-label="Choose evidence pack"
            value={selectedPackId}
            onChange={(e) => setPickedPackId(e.target.value)}
          >
            {packs.map((pack) => (
              <option key={pack.id} value={pack.id}>
                {pack.title}
              </option>
            ))}
          </select>
        )}

        <label className={styles.modeOption}>
          <input
            type="radio"
            name="evidence-pack-mode"
            checked={mode === "new"}
            onChange={() => setModeOverride("new")}
          />
          Create new pack
        </label>
        {mode === "new" && (
          <TextInput
            label="New pack title"
            placeholder="Pack title"
            value={title}
            maxLength={500}
            onChange={(e) => setTitle(e.target.value)}
          />
        )}
      </fieldset>

      {isDuplicate && (
        <p className={styles.duplicate} role="status">
          This passage is already in the selected pack.
        </p>
      )}
      {saveMutation.isError && (
        <p className={styles.error} role="alert">
          {saveErrorMessage(saveMutation.error)}
        </p>
      )}

      <div className={styles.actions}>
        <Button variant="secondary" onClick={onClose} disabled={saveMutation.isPending}>
          Cancel
        </Button>
        <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending} disabled={!canSave}>
          <BookmarkPlus size={14} />
          Save
        </Button>
      </div>
    </div>
  );
}

export function SaveToEvidencePackDialog({
  open,
  onClose,
  draft,
  createdFrom,
}: SaveToEvidencePackDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} title="Save to evidence pack">
      <SaveEvidenceForm draft={draft} createdFrom={createdFrom} onClose={onClose} />
    </Dialog>
  );
}
