import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { getActivity } from "@/api/history";
import { EmptyState } from "@/components/primitives/EmptyState";
import { useT, type Translations } from "@/i18n/index";
import styles from "./HistoryPage.module.css";

function mimeShortLabel(mime: string, t: Translations): string {
  if (mime.startsWith("image/")) return t.history.mimeImage;
  if (mime === "application/pdf") return t.history.mimePdf;
  if (mime.includes("msword") || mime.includes("wordprocessingml")) return t.history.mimeWord;
  if (mime.includes("excel") || mime.includes("spreadsheet")) return t.history.mimeExcel;
  if (mime.includes("powerpoint") || mime.includes("presentation")) return t.history.mimePpt;
  if (mime === "text/html") return t.history.mimeHtml;
  if (mime === "text/plain") return t.history.mimeText;
  if (mime === "message/rfc822") return t.history.mimeEmail;
  return t.history.mimeFile;
}

export function HistoryPage() {
  const t = useT();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({ queryKey: ["history"], queryFn: () => getActivity() });
  const items = data ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{t.history.title}</h1>
        <p className={styles.privacy}>{t.history.privacy}</p>
      </header>
      <div className={styles.body}>
        {isLoading && <p className={styles.muted}>{t.history.loading}</p>}
        {isError && <EmptyState title={t.history.failedTitle} body={t.history.failedBody} />}
        {!isLoading && !isError && items.length === 0 && (
          <EmptyState title={t.history.emptyTitle} body={t.history.emptyBody} />
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
                    <span className={styles.docTitle}>{item.title || t.history.untitled}</span>
                    <span className={styles.docMeta}>{mimeShortLabel(item.mime_type, t)}</span>
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
