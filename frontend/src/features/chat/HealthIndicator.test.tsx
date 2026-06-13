import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { HealthIndicator } from "./HealthIndicator";
import type { EvidenceHealthSummary } from "@/api/health";

const HEALTHY_SUMMARY: EvidenceHealthSummary = {
  status: "healthy",
  severity: "info",
  issue_count: 0,
  issues: [],
  latest_check_at: "2026-06-13T12:00:00Z",
};

const DEGRADED_SUMMARY: EvidenceHealthSummary = {
  status: "degraded",
  severity: "warning",
  issue_count: 2,
  issues: [
    {
      code: "empty_chunks",
      label: "Some indexed documents have empty content text",
      severity: "warning",
      safe_message: "Some indexed documents have empty content text",
    },
    {
      code: "ocr_maybe_needed",
      label: "Some PDFs may need OCR processing",
      severity: "warning",
      safe_message: "Some PDFs may need OCR processing",
    },
  ],
  latest_check_at: "2026-06-13T12:00:00Z",
};

const FAILED_SUMMARY: EvidenceHealthSummary = {
  status: "failed",
  severity: "critical",
  issue_count: 1,
  issues: [
    {
      code: "missing_content",
      label: "Some documents are missing content payloads",
      severity: "warning",
      safe_message: "Some documents are missing content payloads",
    },
  ],
  latest_check_at: "2026-06-13T12:00:00Z",
};

const UNKNOWN_SUMMARY: EvidenceHealthSummary = {
  status: "unknown",
  severity: null,
  issue_count: 0,
  issues: [],
  latest_check_at: null,
};

describe("HealthIndicator", () => {
  it("renders loading state", () => {
    render(<HealthIndicator summary={undefined} loading={true} />);
    expect(screen.getByText("Source health")).toBeInTheDocument();
  });

  it("renders no-data state when summary is null", () => {
    render(<HealthIndicator summary={null} />);
    expect(
      screen.getByText("No recent source health check available."),
    ).toBeInTheDocument();
  });

  it("renders healthy badge", () => {
    render(<HealthIndicator summary={HEALTHY_SUMMARY} />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("renders degraded badge", () => {
    render(<HealthIndicator summary={DEGRADED_SUMMARY} />);
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });

  it("renders failed badge", () => {
    render(<HealthIndicator summary={FAILED_SUMMARY} />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders unknown badge", () => {
    render(<HealthIndicator summary={UNKNOWN_SUMMARY} />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("does not show expand button when there are no issues", () => {
    render(<HealthIndicator summary={HEALTHY_SUMMARY} />);
    expect(
      screen.queryByLabelText("Expand issues"),
    ).not.toBeInTheDocument();
  });

  it("shows expand button when there are issues", () => {
    render(<HealthIndicator summary={DEGRADED_SUMMARY} />);
    expect(
      screen.getByLabelText("Expand issues"),
    ).toBeInTheDocument();
  });

  it("shows issue list when expand button is clicked", () => {
    render(<HealthIndicator summary={DEGRADED_SUMMARY} />);
    fireEvent.click(screen.getByLabelText("Expand issues"));
    expect(
      screen.getByText("Some indexed documents have empty content text"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Some PDFs may need OCR processing"),
    ).toBeInTheDocument();
  });

  it("toggles issue list on expand button click", () => {
    render(<HealthIndicator summary={DEGRADED_SUMMARY} />);
    const btn = screen.getByLabelText("Expand issues");
    fireEvent.click(btn);
    expect(
      screen.getByText("Some indexed documents have empty content text"),
    ).toBeInTheDocument();
    fireEvent.click(btn);
    expect(
      screen.queryByText("Some indexed documents have empty content text"),
    ).not.toBeInTheDocument();
  });
});
