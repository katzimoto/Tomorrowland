import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Users, ShieldCheck, ShieldX } from "lucide-react";
import { adminApi } from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { EmptyState } from "@/components/primitives/EmptyState";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import styles from "./AdminSourcesPage.module.css";

export function AdminUsersPage() {
  const navigate = useNavigate();
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.listUsers,
  });

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <Button variant="secondary" size="sm" onClick={() => navigate({ to: "/admin" })}>
          <ArrowLeft size={16} />
          Back
        </Button>
        <h1 className={styles.title}>Users</h1>
      </div>

      {isLoading ? (
        <SkeletonRow count={5} className={styles.skeletons} />
      ) : users.length === 0 ? (
        <EmptyState
          icon={<Users size={32} />}
          title="No users"
          body="No users found."
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Email</th>
                <th>Display name</th>
                <th>Admin</th>
                <th>Source</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className={styles.nameCell}>
                    <a
                      href={`/admin/users/${u.id}`}
                      onClick={(e) => {
                        e.preventDefault();
                        void navigate({
                          to: "/admin/users/$userId",
                          params: { userId: u.id },
                        });
                      }}
                    >
                      {u.email}
                    </a>
                  </td>
                  <td>{u.display_name ?? "—"}</td>
                  <td>
                    {u.is_admin ? (
                      <ShieldCheck size={16} className={styles.adminIcon} />
                    ) : (
                      <ShieldX size={16} className={styles.nonAdminIcon} />
                    )}
                  </td>
                  <td>{u.auth_source}</td>
                  <td className={styles.mutedMeta}>
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
