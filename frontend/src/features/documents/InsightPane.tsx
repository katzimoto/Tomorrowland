import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { Trash2, ChevronDown, ChevronRight } from "lucide-react";
import {
  getSummary,
  getEntities,
  getTags,
  getRelated,
  listDocumentVersions,
} from "@/api/documents";
import {
  listAnnotations,
  createAnnotation,
  deleteAnnotation,
  type Annotation,
} from "@/api/annotations";
import { VersionBadge } from "./VersionBadge";
import { DetailsTab } from "./DetailsTab";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { Tabs } from "@/components/primitives/Tabs";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { DocumentChatPanel } from "@/features/chat/DocumentChatPanel";
import type { DocumentPreview } from "@/api/documents";
import type { InsightPaneTab } from "./insightPaneTabs";
import styles from "./InsightPane.module.css";

interface InsightPaneProps {
  docId: string;
  preview?: DocumentPreview;
}

export function InsightPane({ docId, preview }: InsightPaneProps) {
  const t = useT();
  const [activeTab, setActiveTab] = useState<InsightPaneTab>("summary");

  const TABS: { id: InsightPaneTab; label: string }[] = [
    { id: "summary", label: t.insight.tabSummary },
    { id: "chat", label: t.insight.tabChat },
    { id: "related", label: t.insight.tabRelated },
    { id: "annotations", label: t.insight.tabAnnotations },
    { id: "subscriptions", label: t.insight.tabSubscriptions },
    { id: "versions", label: t.insight.tabVersions },
    { id: "details", label: t.insight.tabDetails },
  ];

  return (
    <div className={styles.pane}>
      <Tabs
        tabs={TABS}
        active={activeTab}
        onChange={(id) => setActiveTab(id as InsightPaneTab)}
        className={styles.tabs}
      />
      <div className={styles.content}>
        {activeTab === "summary" && <SummaryTab docId={docId} />}
        {activeTab === "chat" && <DocumentChatPanel docId={docId} docTitle={preview?.title} />}
        {activeTab === "related" && <RelatedTab docId={docId} />}
        {activeTab === "annotations" && <AnnotationsTab docId={docId} />}
        {activeTab === "subscriptions" && <SubscriptionsStub />}
        {activeTab === "versions" && <VersionsTab docId={docId} />}
        {activeTab === "details" && preview && <DetailsTab preview={preview} docId={docId} />}
      </div>
    </div>
  );
}

function SummaryTab({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-summary", docId],
    staleTime: 2 * 60_000,
    queryFn: () => getSummary(docId),
    retry: false,
  });

  if (isLoading)
    return (
      <div className={styles.loadingStack}>
        <SkeletonRow compact count={2} />
      </div>
    );
  if (isError)
    return (
      <EmptyState
        title={t.insight.summaryFailedTitle}
        body={t.insight.summaryFailedBody}
      />
    );
  if (!data)
    return (
      <EmptyState
        title={t.insight.summaryEmptyTitle}
        body={t.insight.summaryEmptyBody}
      />
    );

  return (
    <div className={styles.summaryBlock}>
      <p className={styles.summaryText}>{data.summary}</p>
      <p className={styles.meta}>
        {t.insight.generatedBy(
          data.model,
          new Date(data.updated_at).toLocaleDateString()
        )}
      </p>
      <EntitiesSection docId={docId} />
      <TagsSection docId={docId} />
    </div>
  );
}

function EntitiesSection({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-entities", docId],
    staleTime: 2 * 60_000,
    queryFn: () => getEntities(docId),
    retry: false,
  });

  if (isLoading || isError || !data?.entities.length) return null;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionHeading}>{t.insight.entities}</h3>
      <div className={styles.dotList}>
        {data.entities.map((e, i) => (
          <span key={`${e.label}-${e.type}`}>
            {i > 0 && <span className="sep">·</span>}
            <span className="item">{e.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function TagsSection({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-tags", docId],
    staleTime: 2 * 60_000,
    queryFn: () => getTags(docId),
    retry: false,
  });

  if (isLoading || isError || !data?.tags.length) return null;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionHeading}>{t.insight.tags}</h3>
      <div className={styles.dotList}>
        {data.tags.map((tag, i) => (
          <span key={tag}>
            {i > 0 && <span className="sep">·</span>}
            <span className="item">{tag}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function RelatedTab({ docId }: { docId: string }) {
  const t = useT();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-related", docId],
    staleTime: 2 * 60_000,
    queryFn: () => getRelated(docId),
    retry: false,
  });

  if (isLoading)
    return (
      <div className={styles.loadingStack}>
        <SkeletonRow compact count={3} />
      </div>
    );
  if (isError)
    return (
      <EmptyState
        title={t.insight.relatedFailedTitle}
        body={t.insight.relatedFailedBody}
      />
    );
  if (!data?.related.length)
    return (
      <EmptyState
        title={t.insight.relatedEmptyTitle}
        body={t.insight.relatedEmptyBody}
      />
    );

  return (
    <ul className={styles.relatedList}>
      {data.related.map((doc) => {
        const isExpanded = expandedId === doc.document_id;
        return (
          <li key={doc.document_id}>
            <Link
              to="/doc/$docId"
              params={{ docId: doc.document_id }}
              className={styles.relatedLink}
            >
              <span className={styles.relatedTitle}>{doc.title || doc.document_id.slice(0, 8)}</span>
              <div style={{ display: "flex", gap: 4, flexShrink: 0, alignItems: "center" }}>
                {doc.reasons?.slice(0, 2).map((r) => (
                  <Badge key={r.type} variant="neutral">{r.label}</Badge>
                ))}
                {doc.reasons && doc.reasons.length > 0 && (
                  <button
                    type="button"
                    className={styles.relatedLink}
                    style={{ padding: "2px 4px", border: "none", background: "none", cursor: "pointer" }}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setExpandedId(isExpanded ? null : doc.document_id);
                    }}
                    aria-label="Why related?"
                  >
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                )}
              </div>
            </Link>
            {isExpanded && doc.reasons && (
              <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--color-text-secondary)", background: "var(--color-bg)", borderRadius: 4 }}>
                <p style={{ fontWeight: 600, marginBottom: 4 }}>Why related?</p>
                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                  {doc.reasons.map((r) => (
                    <li key={r.type} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <Badge variant="neutral">{r.label}</Badge>
                      {r.weight && (
                        <span style={{ color: "var(--color-text-secondary)" }}>
                          (score: {r.weight})
                        </span>
                      )}
                      {r.items && r.items.length > 0 && (
                        <span style={{ color: "var(--color-text-primary)", fontSize: 11 }}>
                          {r.items.join(", ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
                {doc.relation_score != null && (
                  <p style={{ marginTop: 4 }}>
                    Relation score: <strong>{doc.relation_score}</strong>
                  </p>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function AnnotationsTab({ docId }: { docId: string }) {
  const t = useT();
  const [newText, setNewText] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const { show: showToast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["annotations", docId],
    staleTime: 2 * 60_000,
    queryFn: () => listAnnotations(docId),
  });

  const invalidate = () =>
    void qc.invalidateQueries({ queryKey: ["annotations", docId] });

  const addMut = useMutation({
    mutationFn: (body: string) =>
      createAnnotation(docId, { body, shared: !isPrivate, position: null }),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["annotations", docId] });
      const previous = qc.getQueryData<Annotation[]>([
        "annotations",
        docId,
      ]);
      const optimistic: Annotation = {
        id: `optimistic-${Date.now()}`,
        document_id: docId,
        author_id: "current-user",
        author_name: "Reader",
        body,
        position: null,
        shared: !isPrivate,
        created_at: new Date().toISOString(),
        updated_at: null,
        can_modify: true,
      };
      qc.setQueryData<Annotation[]>(
        ["annotations", docId],
        (current) => [...(current ?? []), optimistic]
      );
      setNewText("");
      return { previous };
    },
    onError: (_error, _body, context) => {
      if (context?.previous)
        qc.setQueryData(["annotations", docId], context.previous);
      showToast("error", t.insight.annotationAddError);
    },
    onSettled: invalidate,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAnnotation(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["annotations", docId] });
      const previous = qc.getQueryData<Annotation[]>([
        "annotations",
        docId,
      ]);
      qc.setQueryData<Annotation[]>(
        ["annotations", docId],
        (current) => (current ?? []).filter(
          (annotation) => annotation.id !== id
        )
      );
      return { previous };
    },
    onError: (_error, _id, context) => {
      if (context?.previous)
        qc.setQueryData(["annotations", docId], context.previous);
      showToast("error", t.insight.annotationDeleteError);
    },
    onSettled: invalidate,
  });

  const annotations = data ?? [];

  return (
    <div className={styles.commentsSection}>
      {isLoading && (
        <p className={styles.muted}>{t.insight.annotationsLoading}</p>
      )}
      {isError && (
        <EmptyState
          title={t.insight.annotationsFailedTitle}
          body={t.insight.annotationsFailedBody}
        />
      )}
      {!isLoading && !isError && annotations.length === 0 && (
        <p className={styles.muted}>{t.insight.annotationsEmpty}</p>
      )}
      <ul className={styles.commentList}>
        {annotations.map((a) => (
          <li key={a.id} className={styles.comment}>
            <div className={styles.commentMeta}>
              <Badge variant={a.shared ? "source" : "neutral"}>
                {a.shared
                  ? t.insight.annotationShared
                  : t.insight.annotationPrivate}
              </Badge>
              <span className={styles.commentDate}>
                {new Date(a.created_at).toLocaleDateString()}
              </span>
              {a.can_modify && (
                <button
                  className={styles.iconAction}
                  aria-label={t.insight.annotationDeleteLabel}
                  onClick={() => deleteMut.mutate(a.id)}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
            <p className={styles.commentBody}>{a.body}</p>
          </li>
        ))}
      </ul>
      <div className={styles.addComment}>
        <input
          className={styles.inlineInput}
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && newText.trim() && !addMut.isPending) {
              e.preventDefault();
              addMut.mutate(newText.trim());
            }
          }}
          placeholder={t.insight.annotationAddPlaceholder}
          aria-label={t.insight.annotationNewLabel}
        />
        <label className={styles.visibilityLabel}>
          <input
            type="checkbox"
            checked={isPrivate}
            onChange={(e) => setIsPrivate(e.target.checked)}
          />
          {t.insight.annotationPrivateLabel}
        </label>
        <Button
          size="sm"
          onClick={() => addMut.mutate(newText.trim())}
          disabled={!newText.trim() || addMut.isPending}
        >
          {t.insight.annotationAddBtn}
        </Button>
      </div>
    </div>
  );
}

function SubscriptionsStub() {
  const t = useT();
  return (
    <EmptyState
      title={t.insight.subscriptionsTitle}
      body={t.insight.subscriptionsBody}
    />
  );
}

function VersionsTab({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-versions", docId],
    staleTime: 2 * 60_000,
    queryFn: () => listDocumentVersions(docId),
  });

  if (isLoading)
    return (
      <div className={styles.loadingStack}>
        <SkeletonRow compact count={2} />
      </div>
    );
  if (isError)
    return (
      <EmptyState
        title={t.insight.versionsFailedTitle}
        body={t.insight.versionsFailedBody}
      />
    );
  if (!data?.length)
    return <EmptyState title={t.insight.versionsEmpty} body="" />;

  return (
    <ul className={styles.relatedList}>
      {data.map((v) => (
        <li key={v.document_id}>
          <Link
            to="/doc/$docId"
            params={{ docId: v.document_id }}
            className={styles.relatedLink}
          >
            <span className={styles.relatedTitle}>
              {v.title ?? t.insight.versionLabel(v.version_number)}
            </span>
            <VersionBadge
              versionNumber={v.version_number}
              isLatest={v.is_latest}
            />
            <span className={styles.entityCount}>
              {new Date(v.created_at).toLocaleDateString()}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
