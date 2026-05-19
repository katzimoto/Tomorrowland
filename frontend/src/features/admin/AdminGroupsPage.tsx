import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Users } from "lucide-react";
import { adminApi } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import styles from "./AdminSourcesPage.module.css";

export function AdminGroupsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [renameTarget, setRenameTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const { data: groups = [], isLoading } = useQuery({
    queryKey: ["admin-groups"],
    queryFn: adminApi.listGroups,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => adminApi.createGroup(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-groups"] });
      setCreateOpen(false);
      setNewName("");
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      adminApi.renameGroup(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-groups"] });
      setRenameTarget(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteGroup(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-groups"] });
      setDeleteTarget(null);
    },
  });

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Groups</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus size={16} />
          Create group
        </Button>
      </div>

      {isLoading ? (
        <SkeletonRow count={3} className={styles.skeletons} />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={<Users size={32} />}
          title="No groups yet"
          body="Create your first group to organize users and manage permissions."
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.id}>
                  <td className={styles.nameCell}>
                    <a
                      href={`/admin/groups/${g.id}`}
                      onClick={(e) => {
                        e.preventDefault();
                        void navigate({
                          to: "/admin/groups/$groupId",
                          params: { groupId: g.id },
                        });
                      }}
                    >
                      {g.name}
                    </a>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setRenameTarget({ id: g.id, name: g.name })}
                      >
                        <Pencil size={13} />
                        Rename
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => setDeleteTarget({ id: g.id, name: g.name })}
                      >
                        <Trash2 size={13} />
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create dialog */}
      <Dialog
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
          setNewName("");
        }}
        title="Create group"
      >
        <div className={styles.form}>
          <label className={styles.label}>
            Group name
            <input
              className={styles.input}
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. analysts"
              autoFocus
            />
          </label>
          {createMutation.error && (
            <p className={styles.formError} role="alert">
              {createMutation.error instanceof Error
                ? createMutation.error.message
                : "Failed to create group"}
            </p>
          )}
          <div className={styles.dialogActions}>
            <Button
              onClick={() => {
                if (newName.trim()) createMutation.mutate(newName.trim());
              }}
              disabled={!newName.trim()}
              loading={createMutation.isPending}
            >
              Create
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setCreateOpen(false);
                setNewName("");
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Rename dialog */}
      <Dialog
        open={renameTarget !== null}
        onClose={() => setRenameTarget(null)}
        title={`Rename: ${renameTarget?.name ?? ""}`}
      >
        <div className={styles.form}>
          <label className={styles.label}>
            New name
            <input
              className={styles.input}
              type="text"
              defaultValue={renameTarget?.name ?? ""}
              onChange={(e) => {
                if (renameTarget)
                  setRenameTarget({ ...renameTarget, name: e.target.value });
              }}
              autoFocus
            />
          </label>
          {renameMutation.error && (
            <p className={styles.formError} role="alert">
              {renameMutation.error instanceof Error
                ? renameMutation.error.message
                : "Failed to rename group"}
            </p>
          )}
          <div className={styles.dialogActions}>
            <Button
              onClick={() => {
                if (renameTarget && renameTarget.name.trim())
                  renameMutation.mutate(renameTarget);
              }}
              disabled={!renameTarget?.name.trim()}
              loading={renameMutation.isPending}
            >
              Save
            </Button>
            <Button variant="secondary" onClick={() => setRenameTarget(null)}>
              Cancel
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="Delete group"
      >
        <div className={styles.form}>
          <p>
            Are you sure you want to delete <strong>{deleteTarget?.name ?? ""}</strong>?
          </p>
          <p className={styles.warning}>
            This will remove all user memberships and source permission grants for this group.
            Users will lose access to any sources that were only accessible through this group.
            This action cannot be undone.
          </p>
          {deleteMutation.error && (
            <p className={styles.formError} role="alert">
              {deleteMutation.error instanceof Error
                ? deleteMutation.error.message
                : "Failed to delete group"}
            </p>
          )}
          <div className={styles.dialogActions}>
            <Button
              variant="danger"
              onClick={() => {
                if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
              }}
              loading={deleteMutation.isPending}
            >
              Delete
            </Button>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
