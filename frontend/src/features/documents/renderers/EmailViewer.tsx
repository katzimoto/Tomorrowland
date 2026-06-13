import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { getPreviewArtifactText, type PreviewManifest } from "@/api/preview";
import { useT } from "@/i18n";
import { highlightMatches } from "../highlightMatches";
import styles from "./renderers.module.css";

interface EmailViewerProps {
  manifest: PreviewManifest;
  docId: string;
  searchQuery?: string;
  activeSearchIndex?: number;
  onMatchCountChange?: (count: number) => void;
}

type BodyView = "html" | "text";

function formatBytes(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function EmailViewer({
  manifest,
  docId,
  searchQuery = "",
  activeSearchIndex = 0,
  onMatchCountChange,
}: EmailViewerProps) {
  const t = useT();
  const email = manifest.email;
  const hasHtml = email?.has_html_body ?? false;
  const hasText = email?.has_text_body ?? false;
  const [view, setView] = useState<BodyView>(hasHtml ? "html" : "text");
  const bodyRef = useRef<HTMLDivElement>(null);

  // Search only works on the text body (the HTML lives inside a sandboxed
  // iframe we cannot reach into), so force the text view while searching.
  const effectiveView: BodyView = searchQuery ? "text" : view;

  const htmlQuery = useQuery({
    queryKey: ["preview-artifact", docId, "body-html", manifest.cache_key],
    queryFn: () => getPreviewArtifactText(docId, "body-html"),
    enabled: hasHtml && effectiveView === "html",
    staleTime: 5 * 60_000,
  });

  const textQuery = useQuery({
    queryKey: ["preview-artifact", docId, "body-text", manifest.cache_key],
    queryFn: () => getPreviewArtifactText(docId, "body-text"),
    enabled: hasText,
    staleTime: 5 * 60_000,
  });

  const bodyText = textQuery.data ?? "";

  const { nodes: bodyNodes, count: matchCount } = useMemo(
    () => highlightMatches(bodyText, searchQuery, activeSearchIndex, styles.match, styles.activeMatch),
    [bodyText, searchQuery, activeSearchIndex],
  );

  useEffect(() => {
    onMatchCountChange?.(matchCount);
  }, [matchCount, onMatchCountChange]);

  useEffect(() => {
    if (!searchQuery || matchCount === 0) return;
    bodyRef.current
      ?.querySelector<HTMLElement>(`[data-match-index="${activeSearchIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeSearchIndex, searchQuery, matchCount]);

  // Split the text body into main + quoted reply so the thread history can be
  // collapsed. Only applies when not searching (highlight needs one pass).
  const quotedStart = email?.quoted_ranges?.[0]?.start_line ?? null;
  const { mainText, quotedText } = useMemo(() => {
    if (quotedStart == null) return { mainText: bodyText, quotedText: "" };
    const lines = bodyText.split("\n");
    return {
      mainText: lines.slice(0, quotedStart).join("\n"),
      quotedText: lines.slice(quotedStart).join("\n"),
    };
  }, [bodyText, quotedStart]);

  function renderTextBody() {
    if (textQuery.isLoading) return <div className={styles.muted}>{t.preview.loading}</div>;
    if (searchQuery) {
      return <pre className={styles.emailBody}>{matchCount > 0 ? bodyNodes : bodyText}</pre>;
    }
    if (quotedStart != null && quotedText.trim()) {
      return (
        <>
          <pre className={styles.emailBody}>{mainText}</pre>
          <details className={styles.emailQuoted}>
            <summary className={styles.emailQuotedSummary}>{t.preview.showQuoted}</summary>
            <pre className={styles.emailBody}>{quotedText}</pre>
          </details>
        </>
      );
    }
    return <pre className={styles.emailBody}>{bodyText}</pre>;
  }

  function renderHtmlBody() {
    if (htmlQuery.isLoading) return <div className={styles.muted}>{t.preview.loading}</div>;
    if (htmlQuery.isError) return <div className={styles.muted}>{t.preview.bodyUnavailable}</div>;
    return (
      <iframe
        className={styles.emailIframe}
        // sandbox="" blocks scripts, forms, popups, and same-origin access.
        // The body was already nh3-sanitized server-side; this is the second
        // containment layer. Inline images arrive as data: URIs and still load.
        sandbox=""
        srcDoc={htmlQuery.data ?? ""}
        title={t.preview.emailBodyLabel}
      />
    );
  }

  return (
    <div className={styles.emailWrapper} ref={bodyRef} role="region" aria-label={t.preview.emailRegion}>
      <dl className={styles.emailHeaders}>
        {email?.subject && (
          <>
            <dt className={styles.emailHeaderKey}>{t.preview.subject}</dt>
            <dd className={styles.emailHeaderVal}>{email.subject}</dd>
          </>
        )}
        {email?.from && (
          <>
            <dt className={styles.emailHeaderKey}>{t.preview.from}</dt>
            <dd className={styles.emailHeaderVal}>{email.from}</dd>
          </>
        )}
        {email && email.to.length > 0 && (
          <>
            <dt className={styles.emailHeaderKey}>{t.preview.to}</dt>
            <dd className={styles.emailHeaderVal}>{email.to.join(", ")}</dd>
          </>
        )}
        {email && email.cc.length > 0 && (
          <>
            <dt className={styles.emailHeaderKey}>{t.preview.cc}</dt>
            <dd className={styles.emailHeaderVal}>{email.cc.join(", ")}</dd>
          </>
        )}
        {email?.date && (
          <>
            <dt className={styles.emailHeaderKey}>{t.preview.date}</dt>
            <dd className={styles.emailHeaderVal}>{email.date}</dd>
          </>
        )}
      </dl>

      {hasHtml && hasText && !searchQuery && (
        <div className={styles.emailToolbar}>
          <div className={styles.emailViewToggle} role="group" aria-label={t.preview.bodyView}>
            <button
              type="button"
              className={styles.emailViewToggleBtn}
              aria-pressed={view === "html"}
              onClick={() => setView("html")}
            >
              {t.preview.viewFormatted}
            </button>
            <button
              type="button"
              className={styles.emailViewToggleBtn}
              aria-pressed={view === "text"}
              onClick={() => setView("text")}
            >
              {t.preview.viewText}
            </button>
          </div>
        </div>
      )}

      {email && email.blocked_remote_images > 0 && (
        <div className={styles.emailNotice} role="note">
          {t.preview.blockedImages(email.blocked_remote_images)}
        </div>
      )}

      {effectiveView === "html" ? renderHtmlBody() : renderTextBody()}

      {email && email.attachments.length > 0 && (
        <div className={styles.emailAttachments}>
          <p className={styles.emailAttachmentsHeading}>
            {t.preview.attachments(email.attachments.length)}
          </p>
          {email.attachments.map((att, idx) => (
            <div key={`${att.filename}-${idx}`} className={styles.emailAttachment}>
              {att.preview_available && att.document_id ? (
                <Link to="/doc/$docId" params={{ docId: att.document_id }}>
                  {att.filename}
                </Link>
              ) : (
                <span>{att.filename}</span>
              )}
              <span className={styles.emailAttachmentSize}>{formatBytes(att.size_bytes)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
