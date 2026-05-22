import { useEffect, useRef, useState } from "react";
import { MessageSquare } from "lucide-react";
import { useSearch, useNavigate } from "@tanstack/react-router";
import { useT } from "@/i18n/index";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createChatSession, type ChatSession, type ChatScopeType } from "@/api/chat";
import { ChatSidebar } from "./ChatSidebar";
import { ChatWindow } from "./ChatWindow";
import styles from "./ChatPage.module.css";

const VALID_SCOPE_TYPES = new Set<ChatScopeType>([
  "all_accessible_documents",
  "single_document",
  "selected_documents",
  "source",
  "folder",
  "current_search_results",
]);

function parseScopeFromSearch(search: Record<string, unknown>): {
  scope: ChatScopeType | null;
  ids: string[];
} {
  const rawScope = search.scope;
  const rawIds = search.ids;

  if (typeof rawScope !== "string" || !VALID_SCOPE_TYPES.has(rawScope as ChatScopeType)) {
    return { scope: null, ids: [] };
  }
  const ids = typeof rawIds === "string"
    ? rawIds.split(",").map((s) => s.trim()).filter(Boolean)
    : [];
  return { scope: rawScope as ChatScopeType, ids };
}

export function ChatPage() {
  const t = useT();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const routeSearch = useSearch({ from: "/chat" }) as Record<string, unknown>;
  const { scope: urlScope, ids: urlIds } = parseScopeFromSearch(routeSearch);

  const [selectedSession, setSelectedSession] = useState<ChatSession | null>(null);
  const scopeSessionCreated = useRef(false);

  const createMutation = useMutation({
    mutationFn: (args: { scope_type: ChatScopeType; scope_ids: string[] }) =>
      createChatSession({
        scope_type: args.scope_type,
        scope_ids: args.scope_ids,
        title: null,
      }),
    onSuccess: (session) => {
      void qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      setSelectedSession(session);
      // Clear the URL scope params after session creation so refresh doesn't re-create
      void navigate({ to: "/chat", search: {}, replace: true });
    },
  });

  // Auto-create a scoped session when scope params are present in the URL
  useEffect(() => {
    if (!urlScope || scopeSessionCreated.current) return;
    scopeSessionCreated.current = true;
    createMutation.mutate({ scope_type: urlScope, scope_ids: urlIds });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleScopeChange(scopeType: ChatScopeType, scopeIds: string[]) {
    createMutation.mutate({ scope_type: scopeType, scope_ids: scopeIds });
  }

  function handleCreateDefault() {
    createMutation.mutate({
      scope_type: "all_accessible_documents",
      scope_ids: [],
    });
  }

  function handleSessionDeleted(sessionId: string) {
    if (selectedSession?.id === sessionId) {
      setSelectedSession(null);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>{t.chat.pageTitle}</h1>
      </header>
      <div className={styles.body}>
        <ChatSidebar
          selectedId={selectedSession?.id ?? null}
          onSelect={setSelectedSession}
          onSessionCreated={setSelectedSession}
          onSessionDeleted={handleSessionDeleted}
        />
        <main className={styles.main}>
          {selectedSession ? (
            <ChatWindow
              session={selectedSession}
              onRequestNewScope={handleScopeChange}
              isCreatingScope={createMutation.isPending}
            />
          ) : (
            <div className={styles.emptyWrapper}>
              <EmptyState
                title={t.chat.emptyTitle}
                body={t.chat.emptyBody}
                icon={<MessageSquare size={32} />}
                action={
                  <Button
                    onClick={handleCreateDefault}
                    loading={createMutation.isPending}
                  >
                    {t.chat.startChat}
                  </Button>
                }
              />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
