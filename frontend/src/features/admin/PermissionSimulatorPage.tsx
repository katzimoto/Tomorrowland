import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi, type PermissionSimulatorVerdict, type PermissionSimulatorSearchResult } from "@/api/admin";
import styles from "./PermissionSimulatorPage.module.css";

type Tab = "check" | "search" | "audit";

type CheckMode = "source" | "document";

function VerdictBadge({ verdict }: { verdict: string }) {
  const isAllow = verdict === "allow";
  return (
    <span className={`${styles.verdictBadge} ${isAllow ? styles.verdictAllow : styles.verdictDeny}`}>
      {isAllow ? "Allow" : "Deny"}
    </span>
  );
}

function ReasoningList({ paths }: { paths: string[] }) {
  if (!paths.length) return null;
  return (
    <div className={styles.reasoningSection}>
      <h4 className={styles.sectionTitle}>Reasoning Path</h4>
      <ol className={styles.reasoningList}>
        {paths.map((step, i) => (
          <li key={i} className={styles.reasoningItem}>{step}</li>
        ))}
      </ol>
    </div>
  );
}

function GroupChips({ groups, label, highlight }: { groups: string[]; label: string; highlight?: string[] }) {
  if (!groups.length) return null;
  const highlightSet = new Set(highlight ?? []);
  return (
    <div className={styles.chipGroup}>
      <span className={styles.chipLabel}>{label}</span>
      <div className={styles.chipList}>
        {groups.map((g) => (
          <span
            key={g}
            className={`${styles.chip} ${highlightSet.has(g) ? styles.chipHighlight : ""}`}
          >
            {g}
          </span>
        ))}
      </div>
    </div>
  );
}

export function PermissionSimulatorPage() {
  const [activeTab, setActiveTab] = useState<Tab>("check");
  const [checkMode, setCheckMode] = useState<CheckMode>("source");

  // Check form state
  const [checkUserId, setCheckUserId] = useState("");
  const [checkGroupIds, setCheckGroupIds] = useState("");
  const [checkSourceId, setCheckSourceId] = useState("");
  const [checkDocumentId, setCheckDocumentId] = useState("");

  // Search form state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchUserId, setSearchUserId] = useState("");
  const [searchGroupIds, setSearchGroupIds] = useState("");
  const [searchSourceFilter, setSearchSourceFilter] = useState("");
  const [searchMimeFilter, setSearchMimeFilter] = useState("");

  // Audit form state
  const [auditUserId, setAuditUserId] = useState("");
  const [auditGroupIds, setAuditGroupIds] = useState("");
  const [auditSourceId, setAuditSourceId] = useState("");
  const [auditDocumentId, setAuditDocumentId] = useState("");

  // Results state
  const [checkResult, setCheckResult] = useState<PermissionSimulatorVerdict | null>(null);
  const [searchResult, setSearchResult] = useState<PermissionSimulatorSearchResult | null>(null);
  const [auditResult, setAuditResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch users list for autocomplete hints
  const usersQuery = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => adminApi.listUsers(),
  });



  // ── Handlers ──────────────────────────────────────────────────────────

  const parseGroupIds = (raw: string): string[] | null => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    return trimmed.split(",").map((s) => s.trim()).filter(Boolean);
  };

  const handleSourceCheck = useCallback(async () => {
    if (!checkSourceId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.checkSourceAccess({
        source_id: checkSourceId.trim(),
        user_id: checkUserId.trim() || null,
        group_ids: parseGroupIds(checkGroupIds),
      });
      setCheckResult(result);
    } catch (e) {
      setError((e as Error)?.message ?? "Check failed");
    } finally {
      setLoading(false);
    }
  }, [checkSourceId, checkUserId, checkGroupIds]);

  const handleDocumentCheck = useCallback(async () => {
    if (!checkDocumentId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.checkDocumentAccess({
        document_id: checkDocumentId.trim(),
        user_id: checkUserId.trim() || null,
        group_ids: parseGroupIds(checkGroupIds),
      });
      setCheckResult(result);
    } catch (e) {
      setError((e as Error)?.message ?? "Check failed");
    } finally {
      setLoading(false);
    }
  }, [checkDocumentId, checkUserId, checkGroupIds]);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.simulateSearch({
        query: searchQuery.trim(),
        user_id: searchUserId.trim() || null,
        group_ids: parseGroupIds(searchGroupIds),
        top_k: 20,
        source_filter: searchSourceFilter.trim()
          ? searchSourceFilter.split(",").map((s) => s.trim()).filter(Boolean)
          : null,
        mime_type_filter: searchMimeFilter.trim()
          ? searchMimeFilter.split(",").map((s) => s.trim()).filter(Boolean)
          : null,
      });
      setSearchResult(result);
    } catch (e) {
      setError((e as Error)?.message ?? "Search simulation failed");
    } finally {
      setLoading(false);
    }
  }, [searchQuery, searchUserId, searchGroupIds, searchSourceFilter, searchMimeFilter]);

  const handleAudit = useCallback(async () => {
    if (!auditSourceId.trim() && !auditDocumentId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await adminApi.auditAccess({
        user_id: auditUserId.trim() || null,
        group_ids: parseGroupIds(auditGroupIds),
        source_id: auditSourceId.trim() || null,
        document_id: auditDocumentId.trim() || null,
      });
      setAuditResult(result as unknown as Record<string, unknown>);
    } catch (e) {
      setError((e as Error)?.message ?? "Audit failed");
    } finally {
      setLoading(false);
    }
  }, [auditSourceId, auditDocumentId, auditUserId, auditGroupIds]);

  // ── Render ────────────────────────────────────────────────────────────

  const renderUserFields = (
    userId: string,
    setUserId: (v: string) => void,
    groupIds: string,
    setGroupIds: (v: string) => void,
  ) => (
    <div className={styles.formRow}>
      <div className={styles.formField}>
        <label htmlFor="ps-user-id">Simulated User ID (optional)</label>
        <input
          id="ps-user-id"
          type="text"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="UUID of real user, or leave blank"
        />
        {usersQuery.data && userId && (
          <datalist id="ps-users">
            {usersQuery.data.map((u) => (
              <option key={u.id} value={u.id}>{u.email}</option>
            ))}
          </datalist>
        )}
      </div>
      <span className={styles.formOr}>or</span>
      <div className={styles.formField}>
        <label htmlFor="ps-group-ids">Simulated Group IDs (optional)</label>
        <input
          id="ps-group-ids"
          type="text"
          value={groupIds}
          onChange={(e) => setGroupIds(e.target.value)}
          placeholder="Comma-separated group UUIDs"
        />
        <span className={styles.fieldHint}>
          Leave both blank to simulate an anonymous user with no groups.
        </span>
      </div>
    </div>
  );

  const renderCheckTab = () => (
    <div className={styles.tabContent}>
      <p className={styles.tabDesc}>
        Simulate whether a user or group can access a specific source or document.
        Each check returns a detailed verdict with the full reasoning path.
      </p>

      <div className={styles.modeToggle}>
        <button
          type="button"
          className={`${styles.modeBtn} ${checkMode === "source" ? styles.modeBtnActive : ""}`}
          onClick={() => setCheckMode("source")}
        >
          Source Access
        </button>
        <button
          type="button"
          className={`${styles.modeBtn} ${checkMode === "document" ? styles.modeBtnActive : ""}`}
          onClick={() => setCheckMode("document")}
        >
          Document Access
        </button>
      </div>

      <div className={styles.formSection}>
        {renderUserFields(checkUserId, setCheckUserId, checkGroupIds, setCheckGroupIds)}

        {checkMode === "source" ? (
          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label htmlFor="ps-source-id">Source ID</label>
              <input
                id="ps-source-id"
                type="text"
                value={checkSourceId}
                onChange={(e) => setCheckSourceId(e.target.value)}
                placeholder="UUID of ingestion source"
              />
            </div>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={handleSourceCheck}
              disabled={loading || !checkSourceId.trim()}
            >
              {loading ? "Checking…" : "Check Source Access"}
            </button>
          </div>
        ) : (
          <div className={styles.formRow}>
            <div className={styles.formField}>
              <label htmlFor="ps-doc-id">Document ID</label>
              <input
                id="ps-doc-id"
                type="text"
                value={checkDocumentId}
                onChange={(e) => setCheckDocumentId(e.target.value)}
                placeholder="UUID of document"
              />
            </div>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={handleDocumentCheck}
              disabled={loading || !checkDocumentId.trim()}
            >
              {loading ? "Checking…" : "Check Document Access"}
            </button>
          </div>
        )}
      </div>
    </div>
  );

  const renderSearchTab = () => (
    <div className={styles.tabContent}>
      <p className={styles.tabDesc}>
        Simulate what search results a user/group would see. Shows the Meilisearch
        ACL filter that would be applied and up to 20 result titles (safe metadata only).
      </p>

      <div className={styles.formSection}>
        {renderUserFields(searchUserId, setSearchUserId, searchGroupIds, setSearchGroupIds)}

        <div className={styles.formRow}>
          <div className={styles.formField} style={{ flex: 2 }}>
            <label htmlFor="ps-query">Search Query</label>
            <input
              id="ps-query"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Enter search terms…"
            />
          </div>
        </div>

        <div className={styles.formRow}>
          <div className={styles.formField}>
            <label htmlFor="ps-source-filter">Source Filter (optional)</label>
            <input
              id="ps-source-filter"
              type="text"
              value={searchSourceFilter}
              onChange={(e) => setSearchSourceFilter(e.target.value)}
              placeholder="Comma-separated: folder, confluence, jira"
            />
          </div>
          <div className={styles.formField}>
            <label htmlFor="ps-mime-filter">MIME Type Filter (optional)</label>
            <input
              id="ps-mime-filter"
              type="text"
              value={searchMimeFilter}
              onChange={(e) => setSearchMimeFilter(e.target.value)}
              placeholder="Comma-separated: application/pdf"
            />
          </div>
        </div>

        <button
          type="button"
          className={styles.actionBtn}
          onClick={handleSearch}
          disabled={loading || !searchQuery.trim()}
        >
          {loading ? "Simulating…" : "Simulate Search"}
        </button>
      </div>
    </div>
  );

  const renderAuditTab = () => (
    <div className={styles.tabContent}>
      <p className={styles.tabDesc}>
        Run a combined access audit — simulate user/group access against sources
        and documents simultaneously with a unified diagnostic report.
      </p>

      <div className={styles.formSection}>
        {renderUserFields(auditUserId, setAuditUserId, auditGroupIds, setAuditGroupIds)}

        <div className={styles.formRow}>
          <div className={styles.formField}>
            <label htmlFor="ps-audit-source">Source ID (optional)</label>
            <input
              id="ps-audit-source"
              type="text"
              value={auditSourceId}
              onChange={(e) => setAuditSourceId(e.target.value)}
              placeholder="UUID of ingestion source"
            />
          </div>
          <div className={styles.formField}>
            <label htmlFor="ps-audit-doc">Document ID (optional)</label>
            <input
              id="ps-audit-doc"
              type="text"
              value={auditDocumentId}
              onChange={(e) => setAuditDocumentId(e.target.value)}
              placeholder="UUID of document"
            />
          </div>
        </div>

        <button
          type="button"
          className={styles.actionBtn}
          onClick={handleAudit}
          disabled={loading || (!auditSourceId.trim() && !auditDocumentId.trim())}
        >
          {loading ? "Auditing…" : "Run Audit"}
        </button>
      </div>
    </div>
  );

  const renderVerdictResult = (result: PermissionSimulatorVerdict) => (
    <div className={styles.resultCard}>
      <div className={styles.resultHeader}>
        <VerdictBadge verdict={result.verdict} />
        <span className={styles.reasonCategory}>{result.reason_category}</span>
        {result.user_email && (
          <span className={styles.resultMeta}>
            Simulated: {result.user_email}
            {result.is_admin ? " (admin)" : ""}
          </span>
        )}
      </div>

      {result.document_title && (
        <div className={styles.docContext}>
          <span className={styles.docTitle}>{result.document_title}</span>
          {result.document_mime_type && (
            <span className={styles.docMime}>{result.document_mime_type}</span>
          )}
        </div>
      )}

      <ReasoningList paths={result.reasoning_path} />

      <div className={styles.groupsGrid}>
        <GroupChips
          groups={result.effective_groups}
          label="Effective Groups"
          highlight={result.matching_groups}
        />
        <GroupChips
          groups={result.source_permission_groups}
          label="Source Permission Groups"
          highlight={result.matching_groups}
        />
        {result.matching_groups.length > 0 && (
          <GroupChips
            groups={result.matching_groups}
            label="Matching Groups (access granted via)"
          />
        )}
      </div>
    </div>
  );

  const renderSearchResult = (result: PermissionSimulatorSearchResult) => (
    <div className={styles.resultCard}>
      <h3 className={styles.resultTitle}>Search Simulation Result</h3>

      <div className={styles.searchFilterDisplay}>
        <span className={styles.chipLabel}>ACL Filter</span>
        <code className={styles.filterCode}>
          {result.search_filter || "(empty — admin bypass)"}
        </code>
      </div>

      {result.filter_explanation.length > 0 && (
        <ReasoningList
          paths={result.filter_explanation.map(
            (e) => e.step + (e.group_names ? ` [${e.group_names.join(", ")}]` : ""),
          )}
        />
      )}

      <GroupChips
        groups={result.effective_group_names}
        label="Effective Group Names"
      />

      {result.bm25_results && result.bm25_results.length > 0 && (
        <div className={styles.bm25Section}>
          <h4 className={styles.sectionTitle}>
            BM25 Results ({result.bm25_total} total)
          </h4>
          <table className={styles.resultsTable}>
            <thead>
              <tr>
                <th>Document ID</th>
                <th>Title</th>
                <th>Score</th>
                <th>Chunk</th>
              </tr>
            </thead>
            <tbody>
              {result.bm25_results.map((r) => (
                <tr key={r.document_id}>
                  <td className={styles.mono}>{r.document_id.slice(0, 8)}…</td>
                  <td>{r.title ?? "—"}</td>
                  <td>{r.score.toFixed(4)}</td>
                  <td>{r.chunk_index}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result.bm25_error && (
        <div className={styles.errorInline}>
          BM25 query error: {result.bm25_error}
        </div>
      )}

      {result.note && (
        <div className={styles.note}>{result.note}</div>
      )}
    </div>
  );

  const renderAuditResult = (result: Record<string, unknown>) => {
    const checks = result.checks as (PermissionSimulatorVerdict & { type: string; target: string })[] | undefined;
    const simUser = result.simulated_user as Record<string, unknown> | undefined;

    return (
      <div className={styles.resultCard}>
        <h3 className={styles.resultTitle}>Access Audit Report</h3>

        {simUser && (
          <div className={styles.auditUser}>
            <span className={styles.chipLabel}>Simulated User</span>
            <span>{String(simUser.email ?? "")} {simUser.is_admin ? "(admin)" : ""}</span>
            <span className={styles.mono}>id={String(simUser.id ?? "").slice(0, 8)}…</span>
          </div>
        )}

        {checks?.map((check, i) => (
          <div key={i} className={styles.auditCheck}>
            <div className={styles.auditCheckHeader}>
              <span className={styles.auditCheckType}>{check.type}</span>
              <span className={styles.mono}>{check.target.slice(0, 12)}…</span>
              <VerdictBadge verdict={check.verdict} />
            </div>
            <ReasoningList paths={check.reasoning_path} />
            <div className={styles.groupsGrid}>
              <GroupChips
                groups={check.effective_groups}
                label="Effective Groups"
                highlight={check.matching_groups}
              />
              <GroupChips
                groups={check.source_permission_groups}
                label="Source Permissions"
              />
            </div>
          </div>
        )) ?? null}

        {!checks && !!result.error && (
          <div className={styles.errorInline}>{String(result.error)}: {String(result.detail ?? "")}</div>
        )}
      </div>
    );
  };

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Permission Simulator</h1>
      <p className={styles.subtitle}>
        Simulate user and group access to sources, documents, and search queries.
        Diagnose allow/deny reasoning without exposing inaccessible content.
      </p>

      {/* Tabs */}
      <div className={styles.tabs}>
        {(["check", "search", "audit"] as Tab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ""}`}
            onClick={() => {
              setActiveTab(tab);
              setError(null);
            }}
          >
            {tab === "check" ? "Access Check" : tab === "search" ? "Search Simulation" : "Full Audit"}
          </button>
        ))}
      </div>

      {activeTab === "check" && renderCheckTab()}
      {activeTab === "search" && renderSearchTab()}
      {activeTab === "audit" && renderAuditTab()}

      {/* Error */}
      {error && (
        <div className={styles.errorBanner}>
          {error}
        </div>
      )}

      {/* Results */}
      {activeTab === "check" && checkResult && renderVerdictResult(checkResult)}
      {activeTab === "search" && searchResult && renderSearchResult(searchResult)}
      {activeTab === "audit" && auditResult && renderAuditResult(auditResult)}

      {/* Quick reference */}
      <details className={styles.reference}>
        <summary className={styles.referenceSummary}>Quick Reference</summary>
        <div className={styles.referenceContent}>
          <h4>Available Endpoints</h4>
          <table className={styles.referenceTable}>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className={styles.mono}>POST /admin/permission-simulator/check-source</td>
                <td>Simulate source access for a user/group</td>
              </tr>
              <tr>
                <td className={styles.mono}>POST /admin/permission-simulator/check-document</td>
                <td>Simulate document access (resolves source first)</td>
              </tr>
              <tr>
                <td className={styles.mono}>POST /admin/permission-simulator/search</td>
                <td>Simulate search with permission filter</td>
              </tr>
              <tr>
                <td className={styles.mono}>POST /admin/permission-simulator/audit</td>
                <td>Run combined source + document audit</td>
              </tr>
            </tbody>
          </table>

          <h4>Access Decision Rules</h4>
          <ol className={styles.rulesList}>
            <li><strong>Admin bypass:</strong> is_admin=True users always get access</li>
            <li><strong>Group intersection:</strong> effective_groups ∩ source_permissions ≠ ∅ → allow</li>
            <li><strong>Effective groups</strong> = direct groups ∪ ancestor groups (via group_memberships)</li>
            <li><strong>No groups:</strong> non-admin users with zero groups see nothing</li>
            <li><strong>No source permissions:</strong> sources with no grants are admin-only</li>
          </ol>
        </div>
      </details>
    </div>
  );
}
