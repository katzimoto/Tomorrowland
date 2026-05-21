import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { useT } from "@/i18n/index";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createChatSession, type ChatSession } from "@/api/chat";
import { ChatSidebar } from "./ChatSidebar";
import { ChatWindow } from "./ChatWindow";
import styles from "./ChatPage.module.css";

export function ChatPage() {
  const t = useT();
  const qc = useQueryClient();
  const [selectedSession, setSelectedSession] = useState<ChatSession | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      createChatSession({
        scope_type: "all_accessible_documents",
        scope_ids: [],
        title: null,
      }),
    onSuccess: (session) => {
      void qc.invalidateQueries({ queryKey: ["chat-sessions"] });
      setSelectedSession(session);
    },
  });

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
            <ChatWindow session={selectedSession} />
          ) : (
            <div className={styles.emptyWrapper}>
              <EmptyState
                title={t.chat.emptyTitle}
                body={t.chat.emptyBody}
                icon={<MessageSquare size={32} />}
                action={
                  <Button
                    onClick={() => createMutation.mutate()}
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
