import { useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/index";
import { createChatSession, type ChatSession } from "@/api/chat";
import { ChatWindow } from "./ChatWindow";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import styles from "./DocumentChatPanel.module.css";

interface DocumentChatPanelProps {
  docId: string;
  docTitle?: string | null;
}

export function DocumentChatPanel({ docId, docTitle }: DocumentChatPanelProps) {
  const t = useT();
  const [session, setSession] = useState<ChatSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState(false);
  const seededForDoc = useRef<string | null>(null);

  // Capture docTitle in a ref so the effect only re-runs when docId changes,
  // not when the title arrives asynchronously after the preview loads.
  const docTitleRef = useRef(docTitle);
  docTitleRef.current = docTitle;

  useEffect(() => {
    if (seededForDoc.current === docId) return;
    seededForDoc.current = docId;
    setSession(null);
    setIsLoading(true);
    setIsError(false);
    let cancelled = false;

    createChatSession({
      scope_type: "single_document",
      scope_ids: [docId],
      title: docTitleRef.current ? `Chat: ${docTitleRef.current}` : null,
    })
      .then((s) => {
        if (!cancelled) setSession(s);
      })
      .catch(() => {
        if (!cancelled) setIsError(true);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
      // Allow re-creation if the component is remounted for the same docId
      // (e.g. after an error or tab switch).
      seededForDoc.current = null;
    };
  }, [docId]);

  if (isLoading) {
    return (
      <div className={styles.panel}>
        <div className={styles.loading}>
          <SkeletonRow count={3} />
        </div>
      </div>
    );
  }

  if (isError || !session) {
    return (
      <div className={styles.panel}>
        <EmptyState title={t.chat.loadSessionError} />
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <ChatWindow session={session} />
    </div>
  );
}
