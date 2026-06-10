import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listUserTags,
  addUserTag,
  deleteUserTag,
  type TagVisibility,
  type UserDocumentTag,
} from "@/api/documents";
import { useToast } from "@/components/primitives/ToastContext";
import styles from "./UserTagEditor.module.css";

interface UserTagEditorProps {
  docId: string;
}

export function UserTagEditor({ docId }: UserTagEditorProps) {
  const queryClient = useQueryClient();
  const { show: showToast } = useToast();
  const [input, setInput] = useState("");
  const [visibility, setVisibility] = useState<TagVisibility>("private");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["user-tags", docId],
    queryFn: () => listUserTags(docId),
    staleTime: 60_000,
  });

  const addMutation = useMutation({
    mutationFn: ({ tag, vis }: { tag: string; vis: TagVisibility }) =>
      addUserTag(docId, tag, vis),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["user-tags", docId] });
      setInput("");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message ?? "Failed to add tag");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (tagId: string) => deleteUserTag(docId, tagId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["user-tags", docId] });
    },
    onError: () => {
      showToast("error", "Failed to remove tag");
    },
  });

  function handleAdd() {
    const trimmed = input.trim();
    if (!trimmed) {
      setError("Tag must not be empty");
      return;
    }
    if (trimmed.length > 100) {
      setError("Tag must be 100 characters or fewer");
      return;
    }
    setError(null);
    addMutation.mutate({ tag: trimmed, vis: visibility });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAdd();
    }
  }

  const tags = data?.tags ?? [];

  return (
    <div className={styles.editor}>
      <div className={styles.chipList} aria-label="Your tags" role="list">
        {isLoading && <span className={styles.muted}>Loading…</span>}
        {!isLoading && tags.length === 0 && (
          <span className={styles.muted}>No tags yet</span>
        )}
        {tags.map((tag: UserDocumentTag) => (
          <span
            key={tag.id}
            className={`${styles.chip} ${tag.visibility === "private" ? styles.chipPrivate : styles.chipPublic}`}
            role="listitem"
            title={tag.visibility === "private" ? "Private (only you)" : "Public (all with access)"}
          >
            <span className={styles.chipLabel}>{tag.tag}</span>
            {tag.owned_by_me && (
              <button
                className={styles.chipDelete}
                aria-label={`Remove tag ${tag.tag}`}
                onClick={() => deleteMutation.mutate(tag.id)}
                disabled={deleteMutation.isPending}
              >
                ×
              </button>
            )}
          </span>
        ))}
      </div>

      <div className={styles.addRow}>
        <input
          className={styles.input}
          type="text"
          placeholder="Add a tag…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          maxLength={100}
          aria-label="New tag text"
        />
        <button
          className={styles.addBtn}
          onClick={handleAdd}
          disabled={addMutation.isPending || !input.trim()}
          aria-label="Add tag"
        >
          {addMutation.isPending ? "Adding…" : "Add"}
        </button>
      </div>

      <div className={styles.visibilityRow} role="radiogroup" aria-label="Tag visibility">
        <label className={styles.visLabel}>
          <input
            type="radio"
            name={`tag-visibility-${docId}`}
            value="private"
            checked={visibility === "private"}
            onChange={() => setVisibility("private")}
          />
          {" "}Private
        </label>
        <label className={styles.visLabel}>
          <input
            type="radio"
            name={`tag-visibility-${docId}`}
            value="public"
            checked={visibility === "public"}
            onChange={() => setVisibility("public")}
          />
          {" "}Public
        </label>
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
