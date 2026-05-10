import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Pencil } from "lucide-react";
import {
  getSummary, getEntities, getTags, getRelated,
  listComments, createComment, updateComment, deleteComment,
  listAnnotations, createAnnotation, deleteAnnotation,
} from "@/api/documents";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { Tabs } from "@/components/primitives/Tabs";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n/index";
import { QAPanel } from "@/features/qa/QAPanel";
import type { InsightPaneTab } from "./insightPaneTabs";
import styles from "./InsightPane.module.css";

interface InsightPaneProps {
  docId: string;
}

export function InsightPane({ docId }: InsightPaneProps) {
  const t = useT();
  const [activeTab, setActiveTab] = useState<InsightPaneTab>("summary");

  const TABS: { id: InsightPaneTab; label: string }[] = [
    { id: "summary", label: t.insight.tabSummary },
    { id: "qa", label: t.insight.tabQa },
    { id: "related", label: t.insight.tabRelated },
    { id: "annotations", label: t.insight.tabAnnotations },
    { id: "comments", label: t.insight.tabComments },
    { id: "subscriptions", label: t.insight.tabSubscriptions },
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
        {activeTab === "qa" && <QAPanel />}
        {activeTab === "related" && <RelatedTab docId={docId} />}
        {activeTab === "annotations" && <AnnotationsTab docId={docId} />}
        {activeTab === "comments" && <CommentsTab docId={docId} />}
        {activeTab === "subscriptions" && <SubscriptionsStub />}
      </div>
    </div>
  );
}

function SummaryTab({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-summary", docId],
    queryFn: () => getSummary(docId),
    retry: false,
  });

  if (isLoading) return <p className={styles.muted}>{t.insight.summaryLoading}</p>;
  if (isError) return <EmptyState title={t.insight.summaryFailedTitle} body={t.insight.summaryFailedBody} />;
  if (!data) return <EmptyState title={t.insight.summaryEmptyTitle} body={t.insight.summaryEmptyBody} />;

  return (
    <div className={styles.summaryBlock}>
      <p className={styles.summaryText}>{data.summary}</p>
      <p className={styles.meta}>{t.insight.generatedBy(data.model, new Date(data.updated_at).toLocaleDateString())}</p>
      <EntitiesSection docId={docId} />
      <TagsSection docId={docId} />
    </div>
  );
}

function EntitiesSection({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-entities", docId],
    queryFn: () => getEntities(docId),
    retry: false,
  });

  if (isLoading || isError || !data?.entities.length) return null;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionHeading}>{t.insight.entities}</h3>
      <ul className={styles.entityList}>
        {data.entities.map((e) => (
          <li key={`${e.label}-${e.type}`} className={styles.entityRow}>
            <span className={styles.entityLabel}>{e.label}</span>
            <Badge variant="neutral">{e.type}</Badge>
            <span className={styles.entityCount}>×{e.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TagsSection({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-tags", docId],
    queryFn: () => getTags(docId),
    retry: false,
  });

  if (isLoading || isError || !data?.tags.length) return null;

  return (
    <div className={styles.section}>
      <h3 className={styles.sectionHeading}>{t.insight.tags}</h3>
      <div className={styles.tagCloud}>
        {data.tags.map((tag) => (
          <Badge key={tag} variant="tag">{tag}</Badge>
        ))}
      </div>
    </div>
  );
}

function RelatedTab({ docId }: { docId: string }) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-related", docId],
    queryFn: () => getRelated(docId),
    retry: false,
  });

  if (isLoading) return <p className={styles.muted}>{t.insight.relatedLoading}</p>;
  if (isError) return <EmptyState title={t.insight.relatedFailedTitle} body={t.insight.relatedFailedBody} />;
  if (!data?.related.length) return <EmptyState title={t.insight.relatedEmptyTitle} body={t.insight.relatedEmptyBody} />;

  return (
    <ul className={styles.relatedList}>
      {data.related.map((doc) => (
        <li key={doc.doc_id}>
          <Link to="/doc/$docId" params={{ docId: doc.doc_id }} className={styles.relatedLink}>
            <span className={styles.relatedTitle}>{doc.title}</span>
            <Badge variant="source">{doc.source_label}</Badge>
          </Link>
        </li>
      ))}
    </ul>
  );
}

const PLACEHOLDER_POSITION = { mode: "text-range" as const, start_char: 0, end_char: 0 };

function AnnotationsTab({ docId }: { docId: string }) {
  const t = useT();
  const [newText, setNewText] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const { show: showToast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-annotations", docId],
    queryFn: () => listAnnotations(docId),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["doc-annotations", docId] });

  const addMut = useMutation({
    mutationFn: () => createAnnotation(docId, { text: newText.trim(), position: PLACEHOLDER_POSITION, is_private: isPrivate }),
    onSuccess: () => { setNewText(""); invalidate(); },
    onError: () => showToast("error", t.insight.annotationAddError),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAnnotation(id),
    onSuccess: invalidate,
    onError: () => showToast("error", t.insight.annotationDeleteError),
  });

  const annotations = data?.annotations ?? [];

  return (
    <div className={styles.commentsSection}>
      {isLoading && <p className={styles.muted}>{t.insight.annotationsLoading}</p>}
      {isError && <EmptyState title={t.insight.annotationsFailedTitle} body={t.insight.annotationsFailedBody} />}
      {!isLoading && !isError && annotations.length === 0 && (
        <p className={styles.muted}>{t.insight.annotationsEmpty}</p>
      )}
      <ul className={styles.commentList}>
        {annotations.map((a) => (
          <li key={a.id} className={styles.comment}>
            <div className={styles.commentMeta}>
              <Badge variant={a.is_private ? "neutral" : "source"}>
                {a.is_private ? t.insight.annotationPrivate : t.insight.annotationShared}
              </Badge>
              <span className={styles.commentDate}>{new Date(a.created_at).toLocaleDateString()}</span>
              {a.can_modify && (
                <button className={styles.iconAction} aria-label={t.insight.annotationDeleteLabel} onClick={() => deleteMut.mutate(a.id)}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
            <p className={styles.commentBody}>{a.text}</p>
          </li>
        ))}
      </ul>
      <div className={styles.addComment}>
        <input
          className={styles.inlineInput}
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          placeholder={t.insight.annotationAddPlaceholder}
          aria-label={t.insight.annotationNewLabel}
        />
        <label className={styles.visibilityLabel}>
          <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} />
          {t.insight.annotationPrivateLabel}
        </label>
        <Button size="sm" onClick={() => addMut.mutate()} disabled={!newText.trim() || addMut.isPending}>
          {t.insight.annotationAddBtn}
        </Button>
      </div>
    </div>
  );
}

function CommentsTab({ docId }: { docId: string }) {
  const t = useT();
  const [newBody, setNewBody] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editBody, setEditBody] = useState("");
  const { show: showToast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["doc-comments", docId],
    queryFn: () => listComments(docId),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["doc-comments", docId] });

  const addMut = useMutation({
    mutationFn: () => createComment(docId, newBody.trim()),
    onSuccess: () => { setNewBody(""); invalidate(); },
    onError: () => showToast("error", t.insight.commentPostError),
  });

  const editMut = useMutation({
    mutationFn: () => updateComment(docId, editId!, editBody.trim()),
    onSuccess: () => { setEditId(null); invalidate(); },
    onError: () => showToast("error", t.insight.commentUpdateError),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteComment(docId, id),
    onSuccess: invalidate,
    onError: () => showToast("error", t.insight.commentDeleteError),
  });

  const activeComments = data?.comments.filter((c) => !c.deleted_at) ?? [];

  return (
    <div className={styles.commentsSection}>
      {isLoading && <p className={styles.muted}>{t.insight.commentsLoading}</p>}
      {!isLoading && activeComments.length === 0 && <p className={styles.muted}>{t.insight.commentsEmpty}</p>}
      <ul className={styles.commentList}>
        {activeComments.map((c) => (
          <li key={c.id} className={styles.comment}>
            {editId === c.id ? (
              <div className={styles.commentEditRow}>
                <input className={styles.inlineInput} value={editBody} onChange={(e) => setEditBody(e.target.value)} aria-label={t.insight.commentEditLabel} />
                <Button size="sm" onClick={() => editMut.mutate()} disabled={!editBody.trim() || editMut.isPending}>{t.insight.commentSaveBtn}</Button>
                <Button size="sm" variant="secondary" onClick={() => setEditId(null)}>{t.insight.commentCancelBtn}</Button>
              </div>
            ) : (
              <>
                <div className={styles.commentMeta}>
                  <span className={styles.commentAuthor}>{c.author_display_name}</span>
                  <span className={styles.commentDate}>{new Date(c.created_at).toLocaleDateString()}</span>
                  {c.can_edit && (
                    <button className={styles.iconAction} aria-label={t.insight.commentEditLabel} onClick={() => { setEditId(c.id); setEditBody(c.body); }}>
                      <Pencil size={13} />
                    </button>
                  )}
                  {c.can_delete && (
                    <button className={styles.iconAction} aria-label={t.insight.commentDeleteLabel} onClick={() => deleteMut.mutate(c.id)}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
                <p className={styles.commentBody}>{c.body}</p>
              </>
            )}
          </li>
        ))}
      </ul>
      <div className={styles.addComment}>
        <input
          className={styles.inlineInput}
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          placeholder={t.insight.commentAddPlaceholder}
          aria-label={t.insight.commentNewLabel}
        />
        <Button size="sm" onClick={() => addMut.mutate()} disabled={!newBody.trim() || addMut.isPending}>{t.insight.commentPostBtn}</Button>
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
