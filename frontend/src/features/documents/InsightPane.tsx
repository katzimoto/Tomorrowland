import { useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Pencil } from "lucide-react";
import {
  getSummary, getEntities, getTags, getRelated,
  listComments, createComment, updateComment, deleteComment,
  listAnnotations, createAnnotation, deleteAnnotation,
  type Comment, type CommentListResponse, type DocAnnotation,
} from "@/api/documents";
import { Badge } from "@/components/primitives/Badge";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
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
    staleTime: 2 * 60_000,
    queryFn: () => getSummary(docId),
    retry: false,
  });

  if (isLoading) return <div className={styles.loadingStack}><SkeletonRow compact count={2} /></div>;
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
    staleTime: 2 * 60_000,
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
    staleTime: 2 * 60_000,
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
    staleTime: 2 * 60_000,
    queryFn: () => getRelated(docId),
    retry: false,
  });

  if (isLoading) return <div className={styles.loadingStack}><SkeletonRow compact count={3} /></div>;
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
const COMMENTS_PAGE_SIZE = 20;

function AnnotationsTab({ docId }: { docId: string }) {
  const t = useT();
  const [newText, setNewText] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const { show: showToast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-annotations", docId],
    staleTime: 2 * 60_000,
    queryFn: () => listAnnotations(docId),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["doc-annotations", docId] });

  const addMut = useMutation({
    mutationFn: (text: string) => createAnnotation(docId, { text, position: PLACEHOLDER_POSITION, is_private: isPrivate }),
    onMutate: async (text) => {
      await qc.cancelQueries({ queryKey: ["doc-annotations", docId] });
      const previous = qc.getQueryData<{ annotations: DocAnnotation[] }>(["doc-annotations", docId]);
      const optimistic: DocAnnotation = {
        id: `optimistic-${Date.now()}`,
        doc_id: docId,
        user_id: "current-user",
        text,
        note: null,
        position: PLACEHOLDER_POSITION,
        is_private: isPrivate,
        created_at: new Date().toISOString(),
        can_modify: true,
      };
      qc.setQueryData<{ annotations: DocAnnotation[] }>(["doc-annotations", docId], (current) => ({
        annotations: [...(current?.annotations ?? []), optimistic],
      }));
      setNewText("");
      return { previous };
    },
    onError: (_error, _text, context) => {
      if (context?.previous) qc.setQueryData(["doc-annotations", docId], context.previous);
      showToast("error", t.insight.annotationAddError);
    },
    onSettled: invalidate,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAnnotation(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["doc-annotations", docId] });
      const previous = qc.getQueryData<{ annotations: DocAnnotation[] }>(["doc-annotations", docId]);
      qc.setQueryData<{ annotations: DocAnnotation[] }>(["doc-annotations", docId], (current) => ({
        annotations: (current?.annotations ?? []).filter((annotation) => annotation.id !== id),
      }));
      return { previous };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) qc.setQueryData(["doc-annotations", docId], context.previous);
      showToast("error", t.insight.annotationDeleteError);
    },
    onSettled: invalidate,
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
        <Button size="sm" onClick={() => addMut.mutate(newText.trim())} disabled={!newText.trim() || addMut.isPending}>
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

  const {
    data,
    isLoading,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useInfiniteQuery({
    queryKey: ["doc-comments", docId],
    queryFn: ({ pageParam }) => listComments(docId, pageParam, COMMENTS_PAGE_SIZE),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((count, page) => count + page.comments.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
    staleTime: 2 * 60_000,
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["doc-comments", docId] });

  const addMut = useMutation({
    mutationFn: (body: string) => createComment(docId, body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["doc-comments", docId] });
      const previous = qc.getQueryData<CommentListResponse>(["doc-comments", docId]);
      const optimistic: Comment = {
        id: `optimistic-${Date.now()}`,
        doc_id: docId,
        author_id: "current-user",
        author_display_name: "Reader",
        body,
        created_at: new Date().toISOString(),
        edited_at: null,
        deleted_at: null,
        can_edit: true,
        can_delete: true,
      };
      qc.setQueryData<CommentListResponse>(["doc-comments", docId], (current) => ({
        comments: [...(current?.comments ?? []), optimistic],
        total: (current?.total ?? 0) + 1,
      }));
      setNewBody("");
      return { previous };
    },
    onError: (_error, _body, context) => {
      if (context?.previous) qc.setQueryData(["doc-comments", docId], context.previous);
      showToast("error", t.insight.commentPostError);
    },
    onSettled: invalidate,
  });

  const editMut = useMutation({
    mutationFn: (body: string) => updateComment(docId, editId!, body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["doc-comments", docId] });
      const previous = qc.getQueryData<CommentListResponse>(["doc-comments", docId]);
      const editingId = editId;
      qc.setQueryData<CommentListResponse>(["doc-comments", docId], (current) => ({
        comments: (current?.comments ?? []).map((comment) => comment.id === editingId
          ? { ...comment, body, edited_at: new Date().toISOString() }
          : comment),
        total: current?.total ?? 0,
      }));
      setEditId(null);
      return { previous };
    },
    onError: (_error, _body, context) => {
      if (context?.previous) qc.setQueryData(["doc-comments", docId], context.previous);
      showToast("error", t.insight.commentUpdateError);
    },
    onSettled: invalidate,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteComment(docId, id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["doc-comments", docId] });
      const previous = qc.getQueryData<CommentListResponse>(["doc-comments", docId]);
      qc.setQueryData<CommentListResponse>(["doc-comments", docId], (current) => ({
        comments: (current?.comments ?? []).filter((comment) => comment.id !== id),
        total: Math.max((current?.total ?? 1) - 1, 0),
      }));
      return { previous };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) qc.setQueryData(["doc-comments", docId], context.previous);
      showToast("error", t.insight.commentDeleteError);
    },
    onSettled: invalidate,
  });

  const activeComments = useMemo(
    () => data?.pages.flatMap((page) => page.comments).filter((c) => !c.deleted_at) ?? [],
    [data],
  );

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
                <Button size="sm" onClick={() => editMut.mutate(editBody.trim())} disabled={!editBody.trim() || editMut.isPending}>{t.insight.commentSaveBtn}</Button>
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
      {hasNextPage && (
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void fetchNextPage()}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? t.insight.commentsLoadingMore : t.insight.commentsLoadMore}
        </Button>
      )}
      <div className={styles.addComment}>
        <input
          className={styles.inlineInput}
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          placeholder={t.insight.commentAddPlaceholder}
          aria-label={t.insight.commentNewLabel}
        />
        <Button size="sm" onClick={() => addMut.mutate(newBody.trim())} disabled={!newBody.trim() || addMut.isPending}>{t.insight.commentPostBtn}</Button>
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
