import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getCurrentUser } from "@/api/auth";
import { rerenderPreview, usePreviewManifest } from "@/api/preview";
import { useT } from "@/i18n";
import styles from "./RendererStatusBadge.module.css";

const WORKER_RENDERERS = new Set(["email", "libreoffice_pdf", "sheet_grid"]);

interface RendererStatusBadgeProps {
  docId: string;
}

/**
 * Admin-only diagnostics for the high-fidelity preview render: shows the
 * renderer + status (and the failure category/detail when failed) and a
 * Re-render action. Renders nothing for non-admins or for documents that do
 * not go through a worker renderer.
 */
export function RendererStatusBadge({ docId }: RendererStatusBadgeProps) {
  const t = useT();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { data: user } = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
    staleTime: 5 * 60_000,
  });
  const { data: manifest } = usePreviewManifest(docId);

  if (!user?.is_admin || !manifest || !WORKER_RENDERERS.has(manifest.renderer)) {
    return null;
  }

  async function handleRerender() {
    setBusy(true);
    try {
      await rerenderPreview(docId);
      await queryClient.invalidateQueries({ queryKey: ["preview-manifest", docId] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.badge} role="status">
      <span className={styles.renderer}>{manifest.renderer}</span>
      <span className={`${styles.status} ${styles[manifest.status] ?? ""}`}>
        {manifest.status}
      </span>
      {manifest.status === "failed" && manifest.error && (
        <span className={styles.error}>
          {manifest.error.category}
          {manifest.error.detail ? `: ${manifest.error.detail}` : ""}
        </span>
      )}
      <button
        type="button"
        className={styles.rerenderBtn}
        onClick={handleRerender}
        disabled={busy}
      >
        {busy ? t.preview.loading : t.preview.rerender}
      </button>
    </div>
  );
}
