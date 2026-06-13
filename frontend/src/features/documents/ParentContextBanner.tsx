import { Link } from "@tanstack/react-router";
import type { DocumentRelationship } from "@/api/documents";
import { useT } from "@/i18n";
import styles from "./ParentContextBanner.module.css";

interface ParentContextBannerProps {
  relationships?: DocumentRelationship[] | null;
}

/**
 * Shown on a document that is an attachment/child of another document, so the
 * evidence context ("this came from that email") is visible while previewing.
 */
export function ParentContextBanner({ relationships }: ParentContextBannerProps) {
  const t = useT();
  const parent = relationships?.find((rel) => rel.direction === "parent");
  if (!parent) return null;

  const label = parent.title || parent.other_document_id.slice(0, 8);
  return (
    <div className={styles.banner} role="note">
      <span className={styles.label}>{t.preview.attachmentOf}</span>
      <Link to="/doc/$docId" params={{ docId: parent.other_document_id }} className={styles.link}>
        {label}
      </Link>
    </div>
  );
}
