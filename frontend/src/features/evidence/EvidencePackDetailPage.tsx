import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, ExternalLink, FileJson, Pencil, Trash2 } from "lucide-react";
import {
  getEvidencePack,
  removeEvidencePackItem,
  updateEvidencePack,
  type EvidencePackDetail,
  type EvidencePackItem,
} from "@/api/evidencePacks";
import { ApiError } from "@/api/client";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { ConfirmDialog } from "@/components/primitives/ConfirmDialog";
import { EmptyState } from "@/components/primitives/EmptyState";
import { TextInput } from "@/components/primitives/TextInput";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { useToast } from "@/components/primitives/ToastContext";
import { buildJson, buildMarkdown, downloadTextFile, packFileStem } from "./exportEvidence";
import styles from "./EvidencePackDetailPage.module.css";

/** Group items by their source document, preserving first-seen order. */
function groupByDocument(items: EvidencePackItem[]): [string, EvidencePackItem[]][] {
  const groups = new Map<string, EvidencePackItem[]>();
  for (const item of items) {
    const existing = groups.get(item.document_id);
    if (existing) existing.push(item);
    else groups.set(item.document_id, [item]);
  }
  return [...groups.entries()];
}

function itemRefs(item: EvidencePackItem): string {
  const refs: string[] = [];
  if (item.page_number != null) refs.push(`p. ${item.page_number}`);
  if (item.section_heading) refs.push(item.section_heading);
  if (item.chunk_id) refs.push(`chunk ${item.chunk_id}`);
  return refs.join(" · ");
}

function MetadataEditor({
  pack,
  onDone,
}: {
  pack: EvidencePackDetail;
  onDone: () => void;
}) {
  const { show: showToast } = useToast();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(pack.title);
  const [description, setDescription] = useState(pack.description ?? "");

  const save = useMutation({
    mutationFn: () =>
      updateEvidencePack(pack.id, {
        title: title.trim(),
        description: description.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evidence-pack", pack.id] });
      void queryClient.invalidateQueries({ queryKey: ["evidence-packs"] });
      showToast("success", "Evidence pack updated.");
      onDone();
    },
    onError: () => showToast("error", "Failed to update evidence pack."),
  });

  return (
    <form
      className={styles.editor}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <TextInput label="Title" value={title} maxLength={500} onChange={(e) => setTitle(e.target.value)} />
      <label className={styles.editorLabel}>
        Description
        <textarea
          className={styles.textarea}
          rows={3}
          maxLength={5000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <div className={styles.editorActions}>
        <Button variant="secondary" type="button" onClick={onDone} disabled={save.isPending}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending} disabled={save.isPending || !title.trim()}>
          Save
        </Button>
      </div>
    </form>
  );
}

export function EvidencePackDetailPage() {
  const { packId } = useParams({ from: "/app/evidence/$packId" });
  const { show: showToast } = useToast();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<EvidencePackItem | null>(null);

  const { data: pack, isLoading, isError, error } = useQuery({
    queryKey: ["evidence-pack", packId],
    queryFn: () => getEvidencePack(packId),
  });

  const removeItem = useMutation({
    mutationFn: (item: EvidencePackItem) => removeEvidencePackItem(packId, item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["evidence-pack", packId] });
      showToast("success", "Item removed.");
    },
    onError: () => showToast("error", "Failed to remove item."),
    onSettled: () => setRemoveTarget(null),
  });

  if (isLoading) {
    return (
      <div className={styles.page}>
        <SkeletonRow count={4} />
      </div>
    );
  }

  if (isError || !pack) {
    const status = error instanceof ApiError ? error.status : null;
    return (
      <div className={styles.page}>
        <Link to="/evidence" className={styles.backLink}>
          <ArrowLeft size={14} /> Evidence packs
        </Link>
        <EmptyState
          title={status === 404 ? "Evidence pack not found" : "Could not load evidence pack"}
          body={
            status === 404
              ? "It may have been deleted, or you may not have access to it."
              : "Please try again."
          }
        />
      </div>
    );
  }

  const groups = groupByDocument(pack.items);

  return (
    <div className={styles.page}>
      <Link to="/evidence" className={styles.backLink}>
        <ArrowLeft size={14} /> Evidence packs
      </Link>

      <header className={styles.header}>
        <div className={styles.headerMain}>
          <h1 className={styles.title}>{pack.title}</h1>
          <Badge variant="neutral">{pack.created_from}</Badge>
        </div>
        <div className={styles.headerActions}>
          <Button size="sm" variant="secondary" onClick={() => setEditing((v) => !v)}>
            <Pencil size={14} /> Edit
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              downloadTextFile(`${packFileStem(pack)}.md`, buildMarkdown(pack), "text/markdown")
            }
          >
            <Download size={14} /> Markdown
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              downloadTextFile(
                `${packFileStem(pack)}.json`,
                buildJson(pack),
                "application/json",
              )
            }
          >
            <FileJson size={14} /> JSON
          </Button>
        </div>
      </header>

      {editing ? (
        <MetadataEditor pack={pack} onDone={() => setEditing(false)} />
      ) : (
        pack.description && <p className={styles.description}>{pack.description}</p>
      )}

      {pack.items.length === 0 ? (
        <EmptyState
          title="This evidence pack is empty"
          body="Save citations or passages from chat, search, or the Evidence Inspector to build it up."
        />
      ) : (
        <div className={styles.groups}>
          {groups.map(([documentId, items]) => (
            <section key={documentId} className={styles.group} aria-label={`Document ${documentId}`}>
              <div className={styles.groupHeader}>
                <span className={styles.docId} title={documentId}>
                  {documentId}
                </span>
                <Link
                  to="/doc/$docId"
                  params={{ docId: documentId }}
                  className={styles.openLink}
                  target="_blank"
                >
                  <ExternalLink size={13} /> Open document
                </Link>
              </div>
              <ul className={styles.itemList}>
                {items.map((item) => (
                  <li key={item.id} className={styles.item}>
                    <div className={styles.itemHead}>
                      <Badge variant="neutral">{item.item_type}</Badge>
                      {itemRefs(item) && <span className={styles.refs}>{itemRefs(item)}</span>}
                      <button
                        type="button"
                        className={styles.removeBtn}
                        aria-label="Remove item"
                        onClick={() => setRemoveTarget(item)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <p className={styles.excerpt}>{item.text_excerpt}</p>
                    {item.translated_text && (
                      <p className={styles.translated}>
                        <span className={styles.translatedLabel}>Translated</span>
                        {item.translated_text}
                      </p>
                    )}
                    {item.claim && (
                      <p className={styles.claim}>
                        <span className={styles.claimLabel}>Claim</span>
                        {item.claim}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={removeTarget !== null}
        title="Remove this item?"
        body="The saved excerpt will be removed from this evidence pack."
        confirmLabel="Remove"
        variant="danger"
        onConfirm={() => removeTarget && removeItem.mutate(removeTarget)}
        onClose={() => setRemoveTarget(null)}
      />
    </div>
  );
}
