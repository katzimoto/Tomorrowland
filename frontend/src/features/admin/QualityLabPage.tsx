import { useState, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, type QualityLabRun, type QualityLabRunDetail, type QualityLabTrendPoint } from "@/api/admin";
import styles from "./QualityLabPage.module.css";

type Tab = "runs" | "trends";

const METRIC_OPTIONS: { value: string; label: string }[] = [
  { value: "pass_rate", label: "Pass Rate" },
  { value: "mrr", label: "MRR" },
  { value: "citation_accuracy", label: "Citation Accuracy" },
  { value: "anchor_accuracy", label: "Anchor Accuracy" },
  { value: "expansion_coverage", label: "Expansion Coverage" },
  { value: "no_answer_accuracy", label: "No-Answer Accuracy" },
  { value: "unauthorized_leakage_count", label: "Unauthorized Leakage" },
];

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatFloat(value: number): string {
  return value.toFixed(3);
}

function valueColor(value: number, metric: string): string {
  // Lower is better for leakage count
  if (metric === "unauthorized_leakage_count") {
    return value === 0 ? styles.metricValueGood : styles.metricValueBad;
  }
  if (value >= 0.85) return styles.metricValueGood;
  if (value >= 0.6) return styles.metricValueMedium;
  return styles.metricValueBad;
}

export function QualityLabPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("runs");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [trendMetric, setTrendMetric] = useState("pass_rate");
  const [uploadConfig, setUploadConfig] = useState("default");
  const [uploadStatus, setUploadStatus] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- Queries ---
  const runsQuery = useQuery({
    queryKey: ["quality-lab", "runs"],
    queryFn: () => adminApi.listQualityLabRuns(),
  });

  const runDetailQuery = useQuery({
    queryKey: ["quality-lab", "run", selectedRunId],
    queryFn: () =>
      selectedRunId
        ? adminApi.getQualityLabRun(selectedRunId)
        : Promise.resolve(null),
    enabled: !!selectedRunId,
  });

  const trendsQuery = useQuery({
    queryKey: ["quality-lab", "trends", trendMetric],
    queryFn: () => adminApi.getQualityLabTrends(trendMetric),
    enabled: activeTab === "trends",
  });

  // --- Mutations ---
  const deleteMutation = useMutation({
    mutationFn: (runId: string) => adminApi.deleteQualityLabRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quality-lab"] });
      if (selectedRunId) setSelectedRunId(null);
    },
  });

  // --- Upload handler ---
  const handleUpload = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setUploadStatus(null);

      const reader = new FileReader();
      reader.onload = () => {
        try {
          const raw = JSON.parse(reader.result as string);
          // Accept either {"results": [...]} or a raw array
          const results = Array.isArray(raw) ? raw : raw.results;
          if (!results || !Array.isArray(results)) {
            setUploadStatus({
              type: "error",
              message: "File must contain a JSON object with a 'results' array.",
            });
            return;
          }

          adminApi
            .uploadQualityLabRun({
              results,
              eval_config: uploadConfig,
            })
            .then((res) => {
              setUploadStatus({
                type: "success",
                message: `Run ${res.run_id.slice(0, 8)}… uploaded with ${res.case_count} cases.`,
              });
              queryClient.invalidateQueries({ queryKey: ["quality-lab"] });
            })
            .catch((err) => {
              setUploadStatus({
                type: "error",
                message: err?.message ?? "Upload failed.",
              });
            });
        } catch {
          setUploadStatus({
            type: "error",
            message: "Invalid JSON file.",
          });
        }
      };
      reader.onerror = () => {
        setUploadStatus({
          type: "error",
          message: "Failed to read file.",
        });
      };
      reader.readAsText(file);

      // Reset so the same file can be re-selected
      e.target.value = "";
    },
    [uploadConfig, queryClient],
  );

  // --- Render helpers ---
  const renderMetricChip = (
    label: string,
    value: number,
    metric: string,
    fmt: (v: number) => string = formatPct,
  ) => (
    <div className={styles.metricChip}>
      <span className={styles.metricLabel}>{label}</span>
      <span
        className={`${styles.metricValue} ${valueColor(value, metric)}`}
      >
        {fmt(value)}
      </span>
    </div>
  );

  // --- Run list view ---
  const renderRunsList = () => {
    if (runsQuery.isLoading) {
      return <div className={styles.empty}>Loading runs…</div>;
    }
    if (runsQuery.isError) {
      return (
        <div className={styles.error}>
          Failed to load runs: {(runsQuery.error as Error)?.message}
        </div>
      );
    }
    const runs = runsQuery.data ?? [];
    if (runs.length === 0) {
      return (
        <div className={styles.empty}>
          No eval runs yet. Upload an eval results JSON file to get started.
        </div>
      );
    }

    return (
      <div className={styles.runList}>
        {runs.map((run: QualityLabRun) => (
          <button
            key={run.id}
            type="button"
            className={styles.runCard}
            onClick={() => setSelectedRunId(run.id)}
          >
            <div className={styles.runCardHeader}>
              <span className={styles.runConfig}>{run.eval_config}</span>
              <span className={styles.runMeta}>
                {run.created_at
                  ? new Date(run.created_at).toLocaleDateString()
                  : ""}
                {run.git_commit ? ` · ${run.git_commit.slice(0, 7)}` : ""}
              </span>
            </div>
            <div className={styles.runScoreRow}>
              {renderMetricChip("Pass Rate", run.pass_rate, "pass_rate")}
              {renderMetricChip(
                "MRR",
                (run.summary?.mrr as number | undefined) ?? 0,
                "mrr",
                formatFloat,
              )}
              {renderMetricChip(
                "Citation",
                (run.summary?.citation_accuracy as number | undefined) ?? 0,
                "citation_accuracy",
              )}
              {renderMetricChip(
                "Anchor",
                (run.summary?.anchor_accuracy as number | undefined) ?? 1,
                "anchor_accuracy",
              )}
              {((run.summary?.expansion_cases_total as number | undefined) ?? 0) > 0 &&
                renderMetricChip(
                  "Expansion",
                  (run.summary?.expansion_coverage as number | undefined) ?? 0,
                  "expansion_coverage",
                )}
              {renderMetricChip(
                "No-Ans",
                (run.summary?.no_answer_accuracy as number | undefined) ?? 0,
                "no_answer_accuracy",
              )}
            </div>
          </button>
        ))}
      </div>
    );
  };

  // --- Run detail view ---
  const renderRunDetail = () => {
    if (!selectedRunId) return null;

    if (runDetailQuery.isLoading) {
      return <div className={styles.empty}>Loading run details…</div>;
    }
    if (runDetailQuery.isError) {
      return (
        <div className={styles.error}>
          Failed to load run: {(runDetailQuery.error as Error)?.message}
        </div>
      );
    }
    const detail: QualityLabRunDetail | null | undefined = runDetailQuery.data;
    if (!detail) return null;

    const categories = Array.from(
      new Set(detail.results.map((r) => r.category)),
    );

    return (
      <div>
        <div className={styles.detailHeader}>
          <button
            type="button"
            className={styles.backBtn}
            onClick={() => setSelectedRunId(null)}
          >
            ← Back to runs
          </button>
          <button
            type="button"
            className={styles.deleteBtn}
            onClick={() => {
              if (
                window.confirm(
                  `Delete run ${detail.eval_config}? This cannot be undone.`,
                )
              ) {
                deleteMutation.mutate(detail.id);
              }
            }}
          >
            Delete
          </button>
        </div>

        <h2 className={styles.detailTitle}>{detail.eval_config}</h2>
        <p className={styles.detailMeta}>
          {detail.created_at
            ? new Date(detail.created_at).toLocaleString()
            : ""}
          {detail.git_commit ? ` · commit ${detail.git_commit.slice(0, 7)}` : ""}
          {" · "}
          {detail.passed_count}/{detail.case_count} passed (
          {formatPct(detail.pass_rate)})
        </p>

        <div className={styles.detailSummary}>
          {renderMetricChip("Pass Rate", detail.pass_rate, "pass_rate")}
          {renderMetricChip("MRR", (detail.summary?.mrr as number | undefined) ?? 0, "mrr", formatFloat)}
          {renderMetricChip(
            "Citation",
            (detail.summary?.citation_accuracy as number | undefined) ?? 0,
            "citation_accuracy",
          )}
          {renderMetricChip(
            "No-Answer",
            (detail.summary?.no_answer_accuracy as number | undefined) ?? 0,
            "no_answer_accuracy",
          )}
          {renderMetricChip(
            "Anchor",
            (detail.summary?.anchor_accuracy as number | undefined) ?? 1,
            "anchor_accuracy",
          )}
          {renderMetricChip(
            "Expansion",
            (detail.summary?.expansion_coverage as number | undefined) ?? 0,
            "expansion_coverage",
          )}
          {renderMetricChip(
            "Leakage",
            (detail.summary?.unauthorized_leakage_count as number | undefined) ?? 0,
            "unauthorized_leakage_count",
            (v) => v.toString(),
          )}
          <div className={styles.metricChip}>
            <span className={styles.metricLabel}>Recall@k</span>
            <span className={styles.metricValue}>
              {detail.summary?.recall_at_k
                ? Object.entries(detail.summary.recall_at_k as Record<string, number>)
                    .map(([k, v]) => `@${k} ${formatPct(v)}`)
                    .join("  ")
                : "—"}
            </span>
          </div>
        </div>

        {categories.map((cat) => {
          const catResults = detail.results.filter((r) => r.category === cat);
          const catPassed = catResults.filter((r) => r.passed).length;
          return (
            <div key={cat}>
              <h3 className={styles.casesHeader}>
                {cat} ({catPassed}/{catResults.length})
              </h3>
              <table className={styles.casesTable}>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Status</th>
                    <th>Tags</th>
                    <th>Excerpt</th>
                  </tr>
                </thead>
                <tbody>
                  {catResults.map((r) => (
                    <tr
                      key={r.case_id}
                      className={
                        r.passed ? styles.caseRowPassed : styles.caseRowFailed
                      }
                    >
                      <td>{r.case_id}</td>
                      <td>
                        <span
                          className={
                            r.passed ? styles.statusPass : styles.statusFail
                          }
                        >
                          {r.passed ? "Pass" : "Fail"}
                        </span>
                      </td>
                      <td>
                        {(r.result_json?.tags as string[] | undefined)?.join(
                          ", ",
                        ) ?? "—"}
                      </td>
                      <td>
                        {(r.result_json?.answer_excerpt as string) ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
    );
  };

  // --- Trends view ---
  const renderTrends = () => {
    if (trendsQuery.isLoading) {
      return <div className={styles.empty}>Loading trends…</div>;
    }
    if (trendsQuery.isError) {
      return (
        <div className={styles.error}>
          Failed to load trends: {(trendsQuery.error as Error)?.message}
        </div>
      );
    }
    const points = trendsQuery.data ?? [];
    if (points.length === 0) {
      return (
        <div className={styles.empty}>
          No trend data available yet. Upload at least one eval run.
        </div>
      );
    }

    const maxVal =
      trendMetric === "unauthorized_leakage_count"
        ? Math.max(1, ...points.map((p) => (p as QualityLabTrendPoint).value))
        : 1;

    return (
      <div className={styles.trendsSection}>
        <div className={styles.trendsHeader}>
          <h3 className={styles.detailTitle}>Metric Trends</h3>
          <select
            className={styles.metricSelect}
            value={trendMetric}
            onChange={(e) => setTrendMetric(e.target.value)}
          >
            {METRIC_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.chartArea}>
          {points.map((point) => {
            const p = point as QualityLabTrendPoint;
            const barWidth =
              maxVal > 0 ? Math.min(100, (p.value / maxVal) * 100) : 0;
            const fmt =
              trendMetric === "unauthorized_leakage_count"
                ? (v: number) => v.toString()
                : formatPct;
            return (
              <div key={p.run_id} className={styles.chartBarRow}>
                <span className={styles.chartLabel}>
                  {p.created_at
                    ? new Date(p.created_at).toLocaleDateString()
                    : p.run_id.slice(0, 8)}
                  {" · "}
                  {p.eval_config}
                </span>
                <div className={styles.chartBarWrap}>
                  <div
                    className={styles.chartBar}
                    style={{
                      width: `${barWidth}%`,
                      background:
                        p.value >= 0.85
                          ? undefined
                          : p.value >= 0.6
                            ? "var(--color-warning)"
                            : "var(--color-error)",
                    }}
                  />
                </div>
                <span className={styles.chartValue}>{fmt(p.value)}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Quality Lab</h1>
      <p className={styles.subtitle}>
        Upload offline eval results and track retrieval quality over time.
      </p>

      {/* Upload */}
      <div className={styles.uploadSection}>
        <h2 className={styles.uploadTitle}>Upload Eval Results</h2>
        <p className={styles.uploadDesc}>
          Upload a JSON file from{" "}
          <code>pytest tests/eval/ --eval --eval-output results.json</code>
        </p>
        <div className={styles.uploadRow}>
          <div className={styles.uploadConfig}>
            <label htmlFor="ql-config">Config name</label>
            <input
              id="ql-config"
              type="text"
              value={uploadConfig}
              onChange={(e) => setUploadConfig(e.target.value)}
              placeholder="default"
            />
          </div>
          <button
            type="button"
            className={styles.uploadBtn}
            onClick={handleUpload}
          >
            Choose JSON file…
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
        </div>
        {uploadStatus && (
          <div
            className={
              uploadStatus.type === "success"
                ? styles.uploadSuccess
                : styles.uploadError
            }
          >
            {uploadStatus.message}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          type="button"
          className={`${styles.tab} ${activeTab === "runs" ? styles.tabActive : ""}`}
          onClick={() => {
            setActiveTab("runs");
            setSelectedRunId(null);
          }}
        >
          Runs
        </button>
        <button
          type="button"
          className={`${styles.tab} ${activeTab === "trends" ? styles.tabActive : ""}`}
          onClick={() => {
            setActiveTab("trends");
            setSelectedRunId(null);
          }}
        >
          Trends
        </button>
      </div>

      {activeTab === "runs" && !selectedRunId && renderRunsList()}
      {activeTab === "runs" && selectedRunId && renderRunDetail()}
      {activeTab === "trends" && renderTrends()}
    </div>
  );
}
