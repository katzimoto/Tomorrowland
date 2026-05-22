import { useT } from "@/i18n/index";
import type { ChatScopeType } from "@/api/chat";
import styles from "./ScopeBadge.module.css";

interface ScopeBadgeProps {
  scopeType: ChatScopeType | string;
  scopeIds?: string[];
  title?: string | null;
}

export function ScopeBadge({ scopeType, scopeIds = [], title }: ScopeBadgeProps) {
  const t = useT();

  function scopeLabel(): string {
    switch (scopeType as ChatScopeType) {
      case "all_accessible_documents":
        return t.chat.scopeAll;
      case "single_document":
        return title ?? t.chat.scopeSingleDocument;
      case "selected_documents":
        return scopeIds.length > 0
          ? t.chat.scopeSelectedDocumentsCount(scopeIds.length)
          : t.chat.scopeSelectedDocuments;
      case "source":
        return t.chat.scopeSource;
      case "folder":
        return t.chat.scopeFolder;
      case "current_search_results":
        return t.chat.scopeSearchResults;
      default:
        return scopeType;
    }
  }

  const label = scopeLabel();

  return (
    <span
      className={styles.badge}
      aria-label={`${t.chat.chattingWith}: ${label}`}
    >
      <span className={styles.prefix}>{t.chat.chattingWith}:</span>
      <span className={styles.label}>{label}</span>
    </span>
  );
}
