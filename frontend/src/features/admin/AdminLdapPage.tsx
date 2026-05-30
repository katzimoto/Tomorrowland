import { useCallback, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Search, Plus, Trash2, ShieldQuestion } from "lucide-react";
import {
  adminApi,
  type LdapGroupSearchResult,
  type LdapGroupMapping,
} from "@/api/admin";
import { Button } from "@/components/primitives/Button";
import { Dialog } from "@/components/primitives/Dialog";
import { EmptyState } from "@/components/primitives/EmptyState";
import { TextInput } from "@/components/primitives/TextInput";
import { SkeletonRow } from "@/components/primitives/Skeleton";
import { Badge } from "@/components/primitives/Badge";
import { useToast } from "@/components/primitives/ToastContext";
import { useT } from "@/i18n";
import styles from "./AdminSourcesPage.module.css";

export function AdminLdapPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const t = useT();

  // --- Search state ---
  const [query, setQuery] = useState("");
  const [searchLimit, setSearchLimit] = useState(25);
  const [searched, setSearched] = useState(false);

  // --- Map dialog state ---
  const [mapTarget, setMapTarget] = useState<LdapGroupSearchResult | null>(
    null,
  );
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [mapError, setMapError] = useState("");

  // --- Delete state ---
  const [deleteTarget, setDeleteTarget] = useState<LdapGroupMapping | null>(
    null,
  );

  // --- Queries ---
  const { data: groups = [], isLoading: groupsLoading } = useQuery({
    queryKey: ["admin-groups-list"],
    queryFn: adminApi.listGroups,
  });

  const {
    data: searchResults = [],
    isFetching: searchLoading,
    isError: searchIsError,
    error: searchErrorObj,
  } = useQuery({
    queryKey: ["admin-ldap-search", query, searchLimit],
    queryFn: () => adminApi.searchLdapGroups(query, searchLimit),
    enabled: searched && query.trim().length > 0,
    retry: false,
  });

  const { data: mappings = [], isLoading: mappingsLoading } = useQuery({
    queryKey: ["admin-ldap-mappings"],
    queryFn: adminApi.listLdapGroupMappings,
  });

  // --- Mutations ---
  const createMapping = useMutation({
    mutationFn: adminApi.createLdapGroupMapping,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-ldap-mappings"] });
      setMapTarget(null);
      setSelectedGroupId("");
      setMapError("");
      showToast("success", t.adminLdap.mappingCreated);
    },
    onError: (err: Error) => setMapError(err.message),
  });

  const deleteMapping = useMutation({
    mutationFn: (id: string) => adminApi.deleteLdapGroupMapping(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-ldap-mappings"] });
      setDeleteTarget(null);
      showToast("success", t.adminLdap.mappingDeleted);
    },
    onError: (err: Error) => showToast("error", err.message),
  });

  // --- Actions ---
  const handleSearch = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!query.trim()) return;
      setSearched(true);
    },
    [query],
  );

  const handleMap = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!mapTarget || !selectedGroupId) {
        setMapError("Please select a target group.");
        return;
      }
      setMapError("");
      await createMapping.mutateAsync({
        ldap_dn: mapTarget.dn,
        ldap_external_id_attr: "objectGUID",
        ldap_external_id: mapTarget.external_id,
        ldap_display_name: mapTarget.display_name,
        target_group_id: selectedGroupId,
      });
    },
    [mapTarget, selectedGroupId, createMapping],
  );

  function openMapDialog(result: LdapGroupSearchResult) {
    setMapTarget(result);
    setSelectedGroupId("");
    setMapError("");
  }

  const isAlreadyMapped = useCallback(
    (dn: string) => mappings.some((m) => m.ldap_dn === dn),
    [mappings],
  );

  function resolveGroupName(groupId: string) {
    return groups.find((g) => g.id === groupId)?.name ?? groupId.slice(0, 8);
  }

  return (
    <div className={styles.page}>
      {/* --- Header --- */}
      <div className={styles.header}>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate({ to: "/admin" })}
        >
          <ArrowLeft size={16} />
          Admin
        </Button>
        <h1 className={styles.title}>{t.adminLdap.title}</h1>
      </div>

      <p className={styles.mutedMeta} style={{ marginBottom: "16px" }}>
        {t.adminLdap.subtitle}
      </p>

      {/* --- Info banner --- */}
      <div
        style={{
          display: "flex",
          gap: "10px",
          alignItems: "flex-start",
          padding: "12px 16px",
          marginBottom: "24px",
          background:
            "color-mix(in srgb, var(--color-warning) 8%, transparent)",
          border:
            "1px solid color-mix(in srgb, var(--color-warning) 25%, transparent)",
          borderRadius: "var(--radius-panel)",
          fontSize: "var(--font-size-meta)",
          color: "var(--color-text-secondary)",
        }}
      >
        <ShieldQuestion
          size={18}
          style={{
            flexShrink: 0,
            color: "var(--color-warning)",
            marginTop: "1px",
          }}
        />
        <div>
          <p style={{ margin: "0 0 4px", fontWeight: 500 }}>
            {t.adminLdap.ephemeralNote}
          </p>
          <p style={{ margin: 0 }}>{t.adminLdap.mappingNote}</p>
        </div>
      </div>

      {/* --- Search Section --- */}
      <form
        className={styles.form}
        onSubmit={handleSearch}
        style={{
          marginBottom: "24px",
          flexDirection: "row",
          alignItems: "flex-end",
        }}
      >
        <div style={{ flex: 1 }}>
          <TextInput
            label={t.adminLdap.searchLabel}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSearched(false);
            }}
            placeholder={t.adminLdap.searchPlaceholder}
          />
        </div>
        <div style={{ width: "100px" }}>
          <TextInput
            label="Limit"
            type="number"
            value={String(searchLimit)}
            onChange={(e) => setSearchLimit(Number(e.target.value) || 25)}
          />
        </div>
        <Button type="submit" loading={searchLoading}>
          <Search size={16} />
          {t.adminLdap.searchBtn}
        </Button>
      </form>

      {/* --- Search Results --- */}
      {searched && query.trim().length > 0 && (
        <>
          <h2
            style={{
              fontSize: "var(--font-size-section-title)",
              fontWeight: "var(--font-weight-section-title)",
              margin: "0 0 12px",
              color: "var(--color-text-primary)",
            }}
          >
            Results &mdash;{" "}
            {searchLoading
              ? t.adminLdap.searchingText
              : `${searchResults.length} group${searchResults.length !== 1 ? "s" : ""}`}
          </h2>
          {searchLoading ? (
            <SkeletonRow count={3} className={styles.skeletons} />
          ) : searchIsError ? (
            <EmptyState
              icon={<ShieldQuestion size={28} />}
              title={t.adminLdap.searchError}
              body={(searchErrorObj as Error)?.message ?? ""}
              action={
                <Button variant="secondary" onClick={() => setSearched(true)}>
                  Retry
                </Button>
              }
            />
          ) : searchResults.length === 0 ? (
            <EmptyState
              icon={<Search size={28} />}
              title={t.adminLdap.searchEmpty}
            />
          ) : (
            <div className={styles.tableWrap} style={{ marginBottom: "32px" }}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t.adminLdap.colName}</th>
                    <th>{t.adminLdap.colDN}</th>
                    <th>{t.adminLdap.colExternalId}</th>
                    <th>{t.adminLdap.colActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {searchResults.map((r) => (
                    <tr key={r.dn}>
                      <td className={styles.nameCell}>{r.display_name}</td>
                      <td
                        className={styles.mutedMeta}
                        style={{
                          maxWidth: "320px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={r.dn}
                      >
                        {r.dn}
                      </td>
                      <td className={styles.mutedMeta}>
                        {r.external_id ?? "—"}
                      </td>
                      <td>
                        {isAlreadyMapped(r.dn) ? (
                          <Badge variant="success">Mapped</Badge>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => openMapDialog(r)}
                          >
                            <Plus size={14} />
                            {t.adminLdap.mapBtn}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* --- Existing Mappings --- */}
      <h2
        style={{
          fontSize: "var(--font-size-section-title)",
          fontWeight: "var(--font-weight-section-title)",
          margin: "0 0 12px",
          color: "var(--color-text-primary)",
        }}
      >
        {t.adminLdap.existingMappings}
      </h2>
      {mappingsLoading ? (
        <SkeletonRow count={3} className={styles.skeletons} />
      ) : mappings.length === 0 ? (
        <EmptyState
          icon={<ShieldQuestion size={28} />}
          title={t.adminLdap.noMappings}
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>LDAP Group</th>
                <th>DN</th>
                <th>Tomorrowland Group</th>
                <th>{t.adminLdap.colActions}</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m) => (
                <tr key={m.id}>
                  <td className={styles.nameCell}>{m.ldap_display_name}</td>
                  <td
                    className={styles.mutedMeta}
                    style={{
                      maxWidth: "280px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={m.ldap_dn}
                  >
                    {m.ldap_dn}
                  </td>
                  <td>
                    <Badge variant="tag">
                      {resolveGroupName(m.target_group_id)}
                    </Badge>
                  </td>
                  <td>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setDeleteTarget(m)}
                    >
                      <Trash2 size={13} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* --- Map Dialog --- */}
      <Dialog
        open={!!mapTarget}
        onClose={() => {
          setMapTarget(null);
          setMapError("");
        }}
        title={t.adminLdap.mapBtn}
      >
        <form className={styles.form} onSubmit={handleMap} noValidate>
          <div className={styles.field}>
            <label className={styles.label}>LDAP Group</label>
            <p
              style={{
                margin: 0,
                fontSize: "var(--font-size-body)",
                fontWeight: 500,
              }}
            >
              {mapTarget?.display_name}
            </p>
            <p
              style={{
                margin: 0,
                fontSize: "var(--font-size-meta)",
                color: "var(--color-text-muted)",
              }}
            >
              {mapTarget?.dn}
            </p>
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="ldap-target-group">
              {t.adminLdap.selectGroupLabel}
            </label>
            <select
              id="ldap-target-group"
              className={styles.select}
              value={selectedGroupId}
              onChange={(e) => setSelectedGroupId(e.target.value)}
            >
              <option value="">
                {groupsLoading
                  ? "Loading groups…"
                  : t.adminLdap.selectGroupPlaceholder}
              </option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
          {mapError && (
            <p className={styles.formError} role="alert">
              {mapError}
            </p>
          )}
          <div className={styles.dialogActions}>
            <Button type="submit" loading={createMapping.isPending}>
              {t.adminLdap.createMappingBtn}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setMapTarget(null);
                setMapError("");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      </Dialog>

      {/* --- Delete Confirmation Dialog --- */}
      <Dialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title={t.adminLdap.deleteMappingLabel}
      >
        {deleteTarget && (
          <>
            <p
              style={{
                marginBottom: "16px",
                color: "var(--color-text-secondary)",
              }}
            >
              {t.adminLdap.deleteMappingConfirm(deleteTarget.ldap_display_name)}
            </p>
            <div className={styles.dialogActions}>
              <Button
                variant="danger"
                onClick={() => deleteMapping.mutate(deleteTarget.id)}
                loading={deleteMapping.isPending}
              >
                <Trash2 size={14} />
                Delete Mapping
              </Button>
              <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
                Cancel
              </Button>
            </div>
          </>
        )}
      </Dialog>
    </div>
  );
}
