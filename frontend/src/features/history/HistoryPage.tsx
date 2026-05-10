import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { getActivity } from "@/api/history";
import { EmptyState } from "@/components/primitives/EmptyState";
import styles from "./HistoryPage.module.css";

function mimeShortLabel(mime: string): string {
  if (mime.startsWith("image/")) return "Image";
  if (mime === "application/pdf") return "PDF";
  if (mime.includes("msword") || mime.includes("wordprocessingml")) return "Word";
  if (mime.includes("excel") || mime.includes("spreadsheet")) return "Excel";
  if (mime.includes("powerpoint") || mime.includes("presentation")) return "PowerPoint";
  if (mime === "text/html") return "HTML";
  if (mime === "text/plain") return "Text";
  if (mime === "message/rfc822") return "Email";
  return "File";
}

export function HistoryPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({ queryKey: ["history"], queryFn: () => getActivity() });
  const items = data ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>History</h1>
        <p className={styles.privacy}>Activity visible only to you and admins.</p>
      </header>
      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>Loading…</p>}
        {isError && <EmptyState title="Failed to load history" body="Could not reach the server." />}
        {!isLoading && !isError && items.length === 0 && (
          <EmptyState title="No history" body="Documents you view will appear here." />
        )}
        {items.length > 0 && (
          <ul className={styles.list}>
            {items.map((item) => (
              <li key={item.doc_id}>
                <button
                  className={styles.row}
                  onClick={() => void navigate({ to: "/doc/$docId", params: { docId: item.doc_id } })}
                >
                  <FileText size={16} className={styles.icon} />
                  <div className={styles.rowMain}>
                    <span className={styles.docTitle}>{item.title || "Untitled document"}</span>
                    <span className={styles.docMeta}>{mimeShortLabel(item.mime_type)}</span>
                  </div>
                  {item.viewed_at && (
                    <span className={styles.date}>{new Date(item.viewed_at).toLocaleDateString()}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
