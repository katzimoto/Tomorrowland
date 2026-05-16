import { useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, X } from "lucide-react";
import { adminApi } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import styles from "./AdminSourcesPage.module.css";

export function AdminGroupDetailPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { groupId } = useParams({ from: "/app/admin/groups/$groupId" });

  const [addingUser, setAddingUser] = useState(false);
  const [addingChild, setAddingChild] = useState(false);
  const [childError, setChildError] = useState<string | null>(null);
  const [confirmRemoveUser, setConfirmRemoveUser] = useState<string | null>(null);
  const [confirmRemoveChild, setConfirmRemoveChild] = useState<string | null>(null);

  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ["admin-group-users", groupId],
    queryFn: () => adminApi.listGroupUsers(groupId!),
    enabled: !!groupId,
  });

  const { data: children, isLoading: childrenLoading } = useQuery({
    queryKey: ["admin-group-children", groupId],
    queryFn: () => adminApi.listGroupChildren(groupId!),
    enabled: !!groupId,
  });

  const { data: allUsers } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => adminApi.listUsers(),
  });

  const { data: allGroups } = useQuery({
    queryKey: ["admin-groups"],
    queryFn: () => adminApi.listGroups(),
  });

  const addUserMutation = useMutation({
    mutationFn: (userId: string) => adminApi.addUserToGroup(groupId!, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-group-users", groupId] });
      setAddingUser(false);
    },
  });

  const removeUserMutation = useMutation({
    mutationFn: (userId: string) => adminApi.removeUserFromGroup(groupId!, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-group-users", groupId] });
      setConfirmRemoveUser(null);
    },
  });

  const addChildMutation = useMutation({
    mutationFn: (childGroupId: string) => adminApi.addChildGroup(groupId!, childGroupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-group-children", groupId] });
      setAddingChild(false);
      setChildError(null);
    },
    onError: async (error: unknown) => {
      const resp = error as { status?: number; json?: () => Promise<{ detail?: string }> };
      if (resp?.status === 409) {
        const body = await resp.json?.();
        setChildError(
          body?.detail ?? "This group cannot be added because it would create a circular group relationship.",
        );
      }
    },
  });

  const removeChildMutation = useMutation({
    mutationFn: (childGroupId: string) => adminApi.removeChildGroup(groupId!, childGroupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-group-children", groupId] });
      setConfirmRemoveChild(null);
    },
  });

  const memberIds = new Set((members ?? []).map((m) => m.id));
  const childIds = new Set((children ?? []).map((c) => c.id));

  const availableUsers = (allUsers ?? []).filter((u) => !memberIds.has(u.id));
  const availableGroups = (allGroups ?? []).filter(
    (g) => g.id !== groupId && !childIds.has(g.id),
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>Group detail</h1>
      </div>

      {/* Users section */}
      <div className={styles.section}>
        <h2>Users in this group</h2>
        {membersLoading ? (
          <SkeletonRow count={3} />
        ) : members && members.length > 0 ? (
          <ul className={styles.groupList}>
            {members.map((m) => (
              <li key={m.id} className={styles.groupItem}>
                <Badge variant="neutral">{m.email}</Badge>
                {m.display_name && (
                  <span className={styles.mutedMeta}>{m.display_name}</span>
                )}
                {confirmRemoveUser === m.id ? (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => removeUserMutation.mutate(m.id)}
                      loading={removeUserMutation.isPending}
                    >
                      Confirm remove
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setConfirmRemoveUser(null)}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <button
                    className={styles.removeBtn}
                    type="button"
                    aria-label={`Remove ${m.email}`}
                    onClick={() => setConfirmRemoveUser(m.id)}
                  >
                    <X size={12} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.mutedMeta}>No users are directly in this group.</p>
        )}

        {addingUser ? (
          <div className={styles.addGroupRow}>
            <select
              className={styles.select}
              aria-label="Select user"
              onChange={(e) => {
                if (e.target.value) {
                  addUserMutation.mutate(e.target.value);
                }
              }}
              value=""
            >
              <option value="" disabled>
                Select a user…
              </option>
              {availableUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email}
                </option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={() => setAddingUser(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setAddingUser(true)}
            disabled={availableUsers.length === 0}
          >
            <Plus size={14} />
            Add user
          </Button>
        )}
      </div>

      {/* Child groups section */}
      <div className={styles.section}>
        <h2>Groups in this group</h2>
        {childrenLoading ? (
          <SkeletonRow count={3} />
        ) : children && children.length > 0 ? (
          <ul className={styles.groupList}>
            {children.map((c) => (
              <li key={c.id} className={styles.groupItem}>
                <Badge variant="neutral">{c.name}</Badge>
                {confirmRemoveChild === c.id ? (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => removeChildMutation.mutate(c.id)}
                      loading={removeChildMutation.isPending}
                    >
                      Confirm remove
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setConfirmRemoveChild(null)}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <button
                    className={styles.removeBtn}
                    type="button"
                    aria-label={`Remove ${c.name}`}
                    onClick={() => setConfirmRemoveChild(c.id)}
                  >
                    <X size={12} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.mutedMeta}>
            No sub-groups. A group can contain users and other groups. Source permissions apply
            to direct and nested members.
          </p>
        )}

        {addingChild ? (
          <div className={styles.addGroupRow}>
            <select
              className={styles.select}
              aria-label="Select group"
              onChange={(e) => {
                if (e.target.value) {
                  setChildError(null);
                  addChildMutation.mutate(e.target.value);
                }
              }}
              value=""
            >
              <option value="" disabled>
                Select a group…
              </option>
              {availableGroups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setAddingChild(false);
                setChildError(null);
              }}
            >
              Cancel
            </Button>
            {childError && <p className={styles.error}>{childError}</p>}
          </div>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setAddingChild(true)}
            disabled={availableGroups.length === 0}
          >
            <Plus size={14} />
            Add group
          </Button>
        )}
      </div>

      {!membersLoading && !childrenLoading && !members?.length && !children?.length && (
        <EmptyState
          title="Empty group"
          body="Add users or sub-groups above to start building the membership hierarchy."
        />
      )}
    </div>
  );
}
