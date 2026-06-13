import { useState, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ExternalLink, X, Copy, Check, Flag } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { getPreview } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { DocumentChatCitation, RetrievalTrace } from "@/api/chat";
import { getSourceHealthSummary } from "@/api/health";
import {
  submitCitationFeedback,
  type CitationFeedbackType,
} from "@/api/citationFeedback";
import { useT } from "@/i18n/index";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { PreviewWithHighlight } from "./PreviewWithHighlight";
import { HealthIndicator } from "./HealthIndicator";
import styles from "./EvidencePanel.module.css";

type TabId = "evidence" | "source" | "retrieval" | "actions";

interface EvidencePanelProps {
  citation: DocumentChatCitation;
  retrievalTrace?: RetrievalTrace | null;
  isAdmin?: boolean;
  onClose: () => void;
}

function locationLine(citation: DocumentChatCitation): string {
  const parts: string[] = [];
  if (citation.page_number != null) parts.push(`p. ${citation.page_number}`);
  if (citation.section_heading) parts.push(citation.section_heading);
  return parts.join(" · ");
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value && value !== 0) return null;
  return (
    <div className={styles.metaRow}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={styles.metaValue}>{value}</span>
    </div>
  );
}

function FeedbackForm({
  citation,
  onSuccess,
}: {
  citation: DocumentChatCitation;
  onSuccess: () => void;
}) {
  const t = useT();
  const [type, setType] = useState<CitationFeedbackType>("wrong_passage");
  const [comment, setComment] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      submitCitationFeedback({
        citation_id: citation.citation_id,
        document_id: citation.document_id,
        feedback_type: type,
        comment: comment.trim() || null,
      }),
    onSuccess: onSuccess,
  });

  const feedbackOptions: { value: CitationFeedbackType; label: string }[] = [
    { value: "correct", label: t.chat.feedbackTypeCorrect },
    { value: "wrong_passage", label: t.chat.feedbackTypeWrongPassage },
    { value: "right_document_wrong_location", label: t.chat.feedbackTypeWrongLocation },
    { value: "missing_better_source", label: t.chat.feedbackTypeMissingSource },
    { value: "unsupported_claim", label: t.chat.feedbackTypeUnsupported },
    { value: "permission_concern", label: t.chat.feedbackTypePermission },
    { value: "other", label: t.chat.feedbackTypeOther },
  ];

  if (mutation.isSuccess) {
    return <p className={styles.feedbackSuccess}>{t.chat.feedbackSuccess}</p>;
  }

  return (
    <form
      className={styles.feedbackForm}
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <fieldset className={styles.feedbackFieldset} disabled={mutation.isPending}>
        {feedbackOptions.map((opt) => (
          <label key={opt.value} className={styles.feedbackOption}>
            <input
              type="radio"
              name="feedback_type"
              value={opt.value}
              checked={type === opt.value}
              onChange={() => setType(opt.value)}
            />
            {opt.label}
          </label>
        ))}
        <label className={styles.feedbackCommentLabel}>
          {t.chat.feedbackComment}
          <textarea
            className={styles.feedbackTextarea}
            rows={2}
            maxLength={500}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </label>
        {mutation.isError && (
          <p className={styles.feedbackError}>{t.chat.feedbackError}</p>
        )}
        <button type="submit" className={styles.feedbackSubmitBtn} disabled={mutation.isPending}>
          {mutation.isPending ? t.chat.feedbackSubmitting : t.chat.feedbackSubmit}
        </button>
      </fieldset>
    </form>
  );
}

export function EvidencePanel({
  citation,
  retrievalTrace,
  isAdmin = false,
  onClose,
}: EvidencePanelProps) {
  const t = useT();
  const [activeTab, setActiveTab] = useState<TabId>("evidence");
  const [showFeedbackForm, setShowFeedbackForm] = useState(false);
  const [copied, setCopied] = useState(false);

  const title = citation.document_title ?? citation.doc_title ?? t.chat.untitledDocument;
  const excerpt = citation.text_excerpt ?? citation.chunk_text ?? "";
  const location = locationLine(citation);

  const tracedCandidate = useMemo(
    () =>
      retrievalTrace?.candidates.find(
        (c) =>
          c.document_id === citation.document_id &&
          (citation.chunk_index == null || c.chunk_index === citation.chunk_index),
      ),
    [retrievalTrace, citation.document_id, citation.chunk_index],
  );

  const { data: preview, isLoading, isError, error } = useQuery({
    queryKey: ["evidence-preview", citation.document_id],
    queryFn: () => getPreview(citation.document_id),
    staleTime: 2 * 60_000,
  });

  const { data: healthSummary, isLoading: healthLoading } = useQuery({
    queryKey: ["source-health-summary", citation.source_id],
    queryFn: () => getSourceHealthSummary(citation.source_id!),
    enabled: !!citation.source_id,
    staleTime: 2 * 60_000,
  });

  const apiStatus = error instanceof ApiError ? error.status : null;

  function handleCopy() {
    const parts = [title];
    if (location) parts.push(location);
    if (excerpt) parts.push(`"${excerpt}"`);
    void navigator.clipboard.writeText(parts.join("\n")).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: "evidence", label: t.chat.evidenceTabEvidence },
    { id: "source", label: t.chat.evidenceTabSource },
    ...(isAdmin ? [{ id: "retrieval" as TabId, label: t.chat.evidenceTabRetrieval }] : []),
    { id: "actions", label: t.chat.evidenceTabActions },
  ];

  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <div className={styles.headerInfo}>
          <span className={styles.headerTitle}>{title}</span>
          {location && <span className={styles.location}>{location}</span>}
        </div>
        <div className={styles.headerActions}>
          <Link
            to="/doc/$docId"
            params={{ docId: citation.document_id }}
            search={{
              page: citation.page_number ?? undefined,
              chunk: citation.chunk_index ?? undefined,
            }}
            className={styles.fullPageLink}
            target="_blank"
            aria-label={t.chat.evidenceOpenFullPage}
          >
            <ExternalLink size={16} />
          </Link>
          <button className={styles.closeBtn} onClick={onClose} aria-label={t.chat.evidenceClose}>
            <X size={18} />
          </button>
        </div>
      </header>

      {/* Tab navigation */}
      <nav className={styles.tabs} role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Evidence tab */}
      {activeTab === "evidence" && (
        <div className={styles.tabContent} role="tabpanel">
          {excerpt && (
            <div className={styles.excerpt}>
              <p className={styles.excerptText}>{excerpt}</p>
            </div>
          )}
          <div className={styles.metaSection}>
            {citation.page_number != null && (
              <MetaRow label={t.chat.evidencePageSection} value={location || `p. ${citation.page_number}`} />
            )}
            {citation.chunk_index != null && (
              <MetaRow label={t.chat.evidenceChunkIndex} value={String(citation.chunk_index)} />
            )}
            {citation.language && (
              <MetaRow label={t.chat.evidenceOriginalLanguage} value={citation.language} />
            )}
            {citation.translated_from && (
              <MetaRow label={t.chat.evidenceTranslatedFrom} value={citation.translated_from} />
            )}
            {tracedCandidate && (
              <>
                {tracedCandidate.backends && tracedCandidate.backends.length > 0 && (
                  <div className={styles.metaRow}>
                    <span className={styles.metaLabel}>{t.chat.evidenceBackends}</span>
                    <span className={styles.backendChips}>
                      {tracedCandidate.backends.map((b) => (
                        <span key={b.backend} className={styles.backendChip}>{b.backend}</span>
                      ))}
                    </span>
                  </div>
                )}
                {tracedCandidate.fused_rank != null && (
                  <MetaRow label={t.chat.evidenceFusedRank} value={String(tracedCandidate.fused_rank)} />
                )}
                {tracedCandidate.reranker_delta && (
                  <MetaRow
                    label={t.chat.evidenceRerankerDelta}
                    value={`${tracedCandidate.reranker_delta.input_rank} → ${tracedCandidate.reranker_delta.output_rank ?? "—"}`}
                  />
                )}
                {tracedCandidate.final_context_rank != null && (
                  <MetaRow label={t.chat.evidenceFinalContextRank} value={`#${tracedCandidate.final_context_rank}`} />
                )}
              </>
            )}
          </div>
          {isLoading && (
            <div className={styles.loadingArea}>
              <SkeletonRow count={4} />
            </div>
          )}
          {isError && (
            <div className={styles.errorState}>
              <p className={styles.errorText}>
                {apiStatus === 403
                  ? t.chat.evidenceForbidden
                  : apiStatus === 404
                    ? t.chat.evidenceNotFound
                    : t.chat.evidenceNoPreview}
              </p>
            </div>
          )}
          {preview && (
            <div className={styles.previewArea}>
              <PreviewWithHighlight preview={preview} citation={citation} />
            </div>
          )}
        </div>
      )}

      {/* Source tab */}
      {activeTab === "source" && (
        <div className={styles.tabContent} role="tabpanel">
          <div className={styles.metaSection}>
            <MetaRow label="Document" value={title} />
            {citation.source_id && (
              <MetaRow label={t.chat.evidenceSourceId} value={citation.source_id} />
            )}
            {citation.source_id && (
              <HealthIndicator
                summary={healthSummary}
                loading={healthLoading}
              />
            )}
            {citation.language && (
              <MetaRow label={t.chat.evidenceOriginalLanguage} value={citation.language} />
            )}
            {citation.translated_from && (
              <MetaRow label={t.chat.evidenceTranslatedFrom} value={citation.translated_from} />
            )}
            <MetaRow label="Score" value={citation.score.toFixed(3)} />
          </div>
        </div>
      )}

      {/* Retrieval tab (admin only) */}
      {activeTab === "retrieval" && isAdmin && (
        <div className={styles.tabContent} role="tabpanel">
          {!retrievalTrace ? (
            <p className={styles.traceEmpty}>{t.chat.evidenceRetrievalNoTrace}</p>
          ) : (
            <>
              <div className={styles.traceHeader}>
                <span className={styles.traceLatency}>
                  {retrievalTrace.total_latency_ms.toFixed(0)} ms
                </span>
                {retrievalTrace.reranker_enabled && (
                  <span className={styles.traceReranked}>{t.chat.evidenceRetrievalReranked}</span>
                )}
                {retrievalTrace.retrieval_degraded && (
                  <span className={styles.traceDegraded}>{t.chat.evidenceRetrievalDegraded}</span>
                )}
              </div>
              {citation.source_id && (
                <div className={styles.metaSection}>
                  <HealthIndicator
                    summary={healthSummary}
                    loading={healthLoading}
                  />
                </div>
              )}
              {retrievalTrace.degraded_backends && retrievalTrace.degraded_backends.length > 0 && (
                <div className={styles.metaSection}>
                  <h4 className={styles.traceHeading}>{t.chat.evidenceRetrievalDegradedBackends}</h4>
                  {retrievalTrace.degraded_backends.map((db) => (
                    <div key={db.backend} className={styles.metaRow}>
                      <span className={styles.metaLabel}>{db.backend}</span>
                      <span className={styles.metaValue}>{db.error_category}</span>
                    </div>
                  ))}
                </div>
              )}
              {(() => {
                const counts = [
                  { label: t.chat.evidenceScopeFiltered, value: retrievalTrace.scope_filtered_count },
                  { label: t.chat.evidenceDedupCount, value: retrievalTrace.dedup_count },
                  { label: t.chat.evidenceScoreThresholdFiltered, value: retrievalTrace.score_threshold_filtered_count },
                  { label: t.chat.evidenceRerankerDropped, value: retrievalTrace.reranker_dropped_count },
                ].filter((item) => (item.value ?? 0) > 0);
                return counts.length > 0 ? (
                  <div className={styles.traceSummary}>
                    {counts.map((item) => (
                      <span key={item.label} className={styles.traceSummaryItem}>
                        {item.label}: {item.value}
                      </span>
                    ))}
                  </div>
                ) : null;
              })()}
              <h4 className={styles.traceHeading}>{t.chat.evidenceRetrievalStages}</h4>
              <table className={styles.traceTable}>
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Count</th>
                    <th>ms</th>
                  </tr>
                </thead>
                <tbody>
                  {retrievalTrace.stages.map((s) => (
                    <tr key={s.stage}>
                      <td>{s.stage}</td>
                      <td>{s.candidate_count}</td>
                      <td>{s.timing_ms.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h4 className={styles.traceHeading}>{t.chat.evidenceRetrievalCandidates}</h4>
              <table className={styles.traceTable}>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Score</th>
                    <th>p.</th>
                    <th>#ctx</th>
                  </tr>
                </thead>
                <tbody>
                  {retrievalTrace.candidates.slice(0, 20).map((c, i) => (
                    <tr key={`${c.document_id}-${i}`}>
                      <td className={styles.truncate}>{c.doc_title ?? c.document_id}</td>
                      <td>{c.score.toFixed(3)}</td>
                      <td>{c.page_number ?? "—"}</td>
                      <td>{c.final_context_rank ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {/* Actions tab */}
      {activeTab === "actions" && (
        <div className={styles.tabContent} role="tabpanel">
          <div className={styles.actionsList}>
            <Link
              to="/doc/$docId"
              params={{ docId: citation.document_id }}
              search={{
                page: citation.page_number ?? undefined,
                chunk: citation.chunk_index ?? undefined,
              }}
              className={styles.actionBtn}
              target="_blank"
            >
              <ExternalLink size={16} />
              {t.chat.evidenceOpenFullPage}
            </Link>
            <button className={styles.actionBtn} onClick={handleCopy}>
              {copied ? <Check size={16} /> : <Copy size={16} />}
              {copied ? t.chat.evidenceCopied : t.chat.evidenceCopyCitation}
            </button>
            <button
              className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
              onClick={() => setShowFeedbackForm((v) => !v)}
            >
              <Flag size={16} />
              {t.chat.evidenceReportBadCitation}
            </button>
          </div>
          {showFeedbackForm && (
            <FeedbackForm
              citation={citation}
              onSuccess={() => setShowFeedbackForm(false)}
            />
          )}
        </div>
      )}
    </aside>
  );
}
