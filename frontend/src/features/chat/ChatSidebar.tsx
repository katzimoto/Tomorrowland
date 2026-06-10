import { useState } from "react";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import {
  listChatSessions,
  createChatSession,
  deleteChatSession,
  type ChatSession,
} from "@/api/chat";
import { ConfirmDialog } from "@/components/primitives/ConfirmDialog";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { Button } from "@/components/primitives/Button";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import styles from "./ChatSidebar.module.css";

interface ChatSidebarProps {
  selectedId: string | null;
  onSelect: (session: ChatSession) => void;
  onSessionCreated: (session: ChatSession) => void;
  onSessionDeleted: (sessionId: string) => void;
}

export function ChatSidebar({
  selectedId,
  onSelect,
  onSessionCreated,
  onSessionDeleted,
}: ChatSidebarProps) {
  const t = useT();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const [deleteTarget, setDeleteTarget] = useState<ChatSession | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: () => listChatSessions({ limit: 50 }),
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createChatSession({
        scope_type: "all_accessible_documents",
        scope_ids: [],
        title: null,
      }),
    onSuccess: (session) => {
      void qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      onSessionCreated(session);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteChatSession(sessionId),
    onSuccess: (_data, sessionId) => {
      void qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      onSessionDeleted(sessionId);
    },
    onError: () => {
      showToast("error", t.chat.deleteError);
    },
  });

  const sessions = data?.sessions ?? [];

  return (
    <aside className={styles.sidebar} aria-label={t.chat.pageTitle}>
      <div className={styles.top}>
        <Button
          size="sm"
          onClick={() => createMutation.mutate()}
          loading={createMutation.isPending}
          className={styles.newBtn}
        >
          {t.chat.newChat}
        </Button>
      </div>

      <div className={styles.list} role="list">
        {isLoading && (
          <div className={styles.loadingArea}>
            <SkeletonRow compact count={4} />
          </div>
        )}
        {isError && (
          <p className={styles.error}>{t.chat.loadChatsError}</p>
        )}
        {!isLoading && !isError && sessions.length === 0 && (
          <p className={styles.empty}>{t.chat.noChatsYet}</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            role="listitem"
            className={`${styles.item} ${s.id === selectedId ? styles.active : ""}`}
          >
            <button
              className={styles.itemBtn}
              onClick={() => onSelect(s)}
              aria-current={s.id === selectedId ? "true" : undefined}
            >
              <span className={styles.itemTitle}>{s.title}</span>
            </button>
            <button
              className={styles.deleteBtn}
              onClick={() => setDeleteTarget(s)}
              aria-label={t.chat.deleteSession}
              title={t.chat.deleteSession}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.chat.deleteSession}
        body="This chat and its history will be permanently deleted."
        confirmLabel="Delete"
        variant="danger"
        loading={deleteMutation.isPending}
        onConfirm={() => { deleteMutation.mutate(deleteTarget!.id); setDeleteTarget(null); }}
        onClose={() => setDeleteTarget(null)}
      />
    </aside>
  );
}
