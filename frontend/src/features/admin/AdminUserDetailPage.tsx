import { useState, useEffect } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, X, ShieldCheck, ShieldX, Check, Ban } from "lucide-react";
import { adminApi, type SourceGroup } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Badge } from "@/components/primitives/Badge";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { EmptyState } from "@/components/primitives/EmptyState";
import styles from "./AdminSourcesPage.module.css";

export function AdminUserDetailPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { userId } = useParams({ from: "/app/admin/users/$userId" });

  const [displayName, setDisplayName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [addingGroup, setAddingGroup] = useState(false);
  const [confirmRemoveGroup, setConfirmRemoveGroup] = useState<string | null>(null);

  const { data: user, isLoading } = useQuery({
    queryKey: ["admin-user", userId],
    queryFn: () => adminApi.getUser(userId!),
    enabled: !!userId,
  });

  const { data: allGroups } = useQuery({
    queryKey: ["admin-groups"],
    queryFn: () => adminApi.listGroups(),
  });

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    if (user) {
      setDisplayName(user.display_name ?? "");
      setIsAdmin(user.is_admin);
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [user]);

  const updateMutation = useMutation({
    mutationFn: (payload: { display_name?: string | null; is_admin?: boolean | null }) =>
      adminApi.updateUser(userId!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-user", userId] });
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setDirty(false);
    },
  });

  const addGroupMutation = useMutation({
    mutationFn: (groupId: string) => adminApi.addUserToGroup(groupId, userId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-user", userId] });
      setAddingGroup(false);
    },
  });

  const removeGroupMutation = useMutation({
    mutationFn: (groupId: string) => adminApi.removeUserFromGroup(groupId, userId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-user", userId] });
      setConfirmRemoveGroup(null);
    },
  });

  const userGroupIds = new Set((user?.groups ?? []).map((g) => g.id));
  const availableGroups = (allGroups ?? []).filter((g) => !userGroupIds.has(g.id));

  if (isLoading) {
    return (
      <div className={styles.page}>
        <SkeletonRow count={5} />
      </div>
    );
  }

  if (!user) {
    return (
      <div className={styles.page}>
        <EmptyState title="User not found" body="This user may have been deleted." />
      </div>
    );
  }

  const saveChanges = () => {
    const payload: { display_name?: string | null; is_admin?: boolean | null } = {};
    if (displayName !== (user.display_name ?? "")) {
      payload.display_name = displayName || null;
    }
    if (isAdmin !== user.is_admin) {
      payload.is_admin = isAdmin;
    }
    if (Object.keys(payload).length > 0) {
      updateMutation.mutate(payload);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin/users" })}>
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>{user.email}</h1>
      </div>

      {/* User info section */}
      <div className={styles.section}>
        <h2>User details</h2>
        <dl className={styles.dl}>
          <dt>Email</dt>
          <dd>{user.email}</dd>
          <dt>Auth source</dt>
          <dd>{user.auth_source}</dd>
          <dt>Created</dt>
          <dd>{user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}</dd>
        </dl>
      </div>

      {/* Edit section */}
      <div className={styles.section}>
        <h2>Edit user</h2>
        <div className={styles.form}>
          <label className={styles.label}>
            Display name
            <input
              className={styles.input}
              type="text"
              value={displayName}
              onChange={(e) => {
                setDisplayName(e.target.value);
                setDirty(true);
              }}
              placeholder="Display name"
            />
          </label>

          <label className={styles.label}>
            <div className={styles.toggleRow}>
              <span>Admin</span>
              <button
                type="button"
                className={styles.toggleBtn}
                onClick={() => {
                  setIsAdmin(!isAdmin);
                  setDirty(true);
                }}
                aria-label={`Toggle admin role: currently ${isAdmin ? "enabled" : "disabled"}`}
              >
                {isAdmin ? <ShieldCheck size={18} /> : <ShieldX size={18} />}
                <span>{isAdmin ? "Admin" : "Non-admin"}</span>
              </button>
            </div>
          </label>

          {updateMutation.error && (
            <p className={styles.formError} role="alert">
              {updateMutation.error instanceof Error
                ? updateMutation.error.message
                : "Failed to update user"}
            </p>
          )}

          {dirty && (
            <div className={styles.dialogActions}>
              <Button onClick={saveChanges} loading={updateMutation.isPending}>
                <Check size={14} />
                Save changes
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setDisplayName(user.display_name ?? "");
                  setIsAdmin(user.is_admin);
                  setDirty(false);
                }}
              >
                <Ban size={14} />
                Cancel
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Group membership section */}
      <div className={styles.section}>
        <h2>Group memberships</h2>
        {user.groups && user.groups.length > 0 ? (
          <ul className={styles.groupList}>
            {user.groups.map((g: SourceGroup) => (
              <li key={g.id} className={styles.groupItem}>
                <Badge variant="neutral">{g.name}</Badge>
                {confirmRemoveGroup === g.id ? (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => removeGroupMutation.mutate(g.id)}
                      loading={removeGroupMutation.isPending}
                    >
                      Confirm remove
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setConfirmRemoveGroup(null)}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  <button
                    className={styles.removeBtn}
                    type="button"
                    aria-label={`Remove from ${g.name}`}
                    onClick={() => setConfirmRemoveGroup(g.id)}
                  >
                    <X size={12} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.mutedMeta}>Not a member of any group.</p>
        )}

        {addingGroup ? (
          <div className={styles.addGroupRow}>
            <select
              className={styles.select}
              aria-label="Select group"
              onChange={(e) => {
                if (e.target.value) {
                  addGroupMutation.mutate(e.target.value);
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
            <Button variant="secondary" size="sm" onClick={() => setAddingGroup(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setAddingGroup(true)}
            disabled={availableGroups.length === 0}
          >
            <Plus size={14} />
            Add to group
          </Button>
        )}
      </div>
    </div>
  );
}
