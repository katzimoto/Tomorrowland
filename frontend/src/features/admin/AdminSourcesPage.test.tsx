import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminSourcesPage } from "./AdminSourcesPage";
import * as adminApi from "@/api/admin";

vi.mock("@/api/admin", () => ({
  adminApi: {
    connectorTypes: vi.fn(),
    listSources: vi.fn(),
    createSource: vi.fn(),
    syncSource: vi.fn(),
    testSource: vi.fn(),
  },
}));

const sourceDefaults = {
  path: null,
  source_language: "en",
  enabled: true,
  created_at: "2025-01-01",
  last_sync_status: null,
  last_sync_indexed: null,
  last_sync_skipped: null,
  last_sync_failed: null,
  last_sync_error: null,
  last_sync_at: null,
  last_validation_status: null,
  last_validation_error: null,
  last_validated_at: null,
} as const;

const mockConnectorTypes = [
  {
    type: "folder",
    label: "Folder",
    fields: [
      {
        key: "path",
        label: "Folder path",
        required: true,
        sensitive: false,
        placeholder: "/data",
      },
    ],
  },
  {
    type: "nifi",
    label: "NiFi",
    fields: [
      {
        key: "base_url",
        label: "NiFi base URL",
        required: true,
        sensitive: false,
        placeholder: "http://nifi:8080",
      },
      { key: "api_token", label: "API token", required: true, sensitive: true, placeholder: "" },
    ],
  },
];

beforeEach(() => {
  vi.mocked(adminApi.adminApi.connectorTypes).mockResolvedValue(mockConnectorTypes);
  vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([]);
  vi.mocked(adminApi.adminApi.testSource).mockResolvedValue({
    source_id: "test",
    status: "ok",
    checked_at: "2026-01-01T00:00:00Z",
  });
  vi.mocked(adminApi.adminApi.syncSource).mockResolvedValue({
    status: "success",
    discovered: 1,
    created: 1,
    skipped: 0,
    enqueued: 1,
    failed_discovery: 0,
    failed_enqueue: 0,
  });
});

describe("AdminSourcesPage", () => {
  it("shows the Sources heading", async () => {
    render(<AdminSourcesPage />);
    expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
  });

  it("shows empty state when there are no sources", async () => {
    render(<AdminSourcesPage />);
    expect(await screen.findByText(/no sources yet/i)).toBeInTheDocument();
  });

  it("renders sources table when sources exist", async () => {
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { ...sourceDefaults, id: "abc-1", name: "Legal Docs", type: "folder", path: "/data/legal" },
    ]);
    render(<AdminSourcesPage />);
    expect(await screen.findByText("Legal Docs")).toBeInTheDocument();
    expect(screen.getByText("folder")).toBeInTheDocument();
    expect(screen.getByText("Never synced")).toBeInTheDocument();
  });


  it("renders last sync state and sync result updates", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      {
        ...sourceDefaults,
        id: "abc-1",
        name: "Legal Docs",
        type: "folder",
        last_sync_status: "failed",
        last_sync_indexed: 2,
        last_sync_skipped: 1,
        last_sync_failed: 1,
        last_sync_error: "Source path does not exist",
        last_sync_at: "2025-01-01T12:00:00Z",
      },
    ]);
    vi.mocked(adminApi.adminApi.syncSource).mockResolvedValue({
      status: "success",
      discovered: 3,
      created: 3,
      skipped: 0,
      enqueued: 3,
      failed_discovery: 0,
      failed_enqueue: 0,
    });

    render(<AdminSourcesPage />);

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/Source path does not exist/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^sync$/i }));

    expect(await screen.findByText(/Indexed: 3/i)).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
    expect(await screen.findByText(/Sync completed/i)).toBeInTheDocument();
  });

  it("shows sanitized connection test errors", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { ...sourceDefaults, id: "abc-1", name: "Secure Source", type: "nifi" },
    ]);
    vi.mocked(adminApi.adminApi.testSource).mockRejectedValue(
      new Error("Connector requires api_token [redacted]"),
    );

    render(<AdminSourcesPage />);

    await screen.findByText("Secure Source");
    await user.click(screen.getByRole("button", { name: /^test$/i }));

    expect(await screen.findByText(/api_token \[redacted\]/i)).toBeInTheDocument();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
  });

  it("shows sanitized sync error from API failure", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { ...sourceDefaults, id: "abc-1", name: "Broken Source", type: "folder" },
    ]);
    vi.mocked(adminApi.adminApi.syncSource).mockRejectedValue(
      new Error("Source path does not exist: /invalid"),
    );

    render(<AdminSourcesPage />);

    await screen.findByText("Broken Source");
    await user.click(screen.getByRole("button", { name: /^sync$/i }));

    expect(await screen.findByText(/Source path does not exist/i)).toBeInTheDocument();
    expect(await screen.findByText(/Sync failed/i)).toBeInTheDocument();
  });

  it("shows green Success badge and Sync completed toast on status: success", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { ...sourceDefaults, id: "src-1", name: "Good Source", type: "folder" },
    ]);
    vi.mocked(adminApi.adminApi.syncSource).mockResolvedValue({
      status: "success",
      discovered: 5,
      created: 5,
      skipped: 1,
      enqueued: 5,
      failed_discovery: 0,
      failed_enqueue: 0,
    });

    render(<AdminSourcesPage />);

    await screen.findByText("Good Source");
    await user.click(screen.getByRole("button", { name: /^sync$/i }));

    expect(await screen.findByText("Success")).toBeInTheDocument();
    expect(await screen.findByText(/Indexed: 5/i)).toBeInTheDocument();
    expect(await screen.findByText(/Sync completed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Partial failure/i)).not.toBeInTheDocument();
  });

  it("shows warning Partial failure badge and warning toast on status: partial_failure", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { ...sourceDefaults, id: "src-2", name: "Partial Source", type: "folder" },
    ]);
    vi.mocked(adminApi.adminApi.syncSource).mockResolvedValue({
      status: "partial_failure",
      discovered: 4,
      created: 3,
      skipped: 0,
      enqueued: 3,
      failed_discovery: 1,
      failed_enqueue: 0,
    });

    render(<AdminSourcesPage />);

    await screen.findByText("Partial Source");
    await user.click(screen.getByRole("button", { name: /^sync$/i }));

    expect(await screen.findByText("Partial failure")).toBeInTheDocument();
    expect(await screen.findByText(/Sync completed with failures/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Success$/i)).not.toBeInTheDocument();
  });

  it("shows danger Failed badge and error toast on status: failed", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { ...sourceDefaults, id: "src-3", name: "Failed Source", type: "folder" },
    ]);
    vi.mocked(adminApi.adminApi.syncSource).mockResolvedValue({
      status: "failed",
      discovered: 0,
      created: 0,
      skipped: 0,
      enqueued: 0,
      failed_discovery: 2,
      failed_enqueue: 0,
    });

    render(<AdminSourcesPage />);

    await screen.findByText("Failed Source");
    await user.click(screen.getByRole("button", { name: /^sync$/i }));

    expect(await screen.findByText(/^Failed$/i)).toBeInTheDocument();
    expect(await screen.findByText(/Sync failed/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Success$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Partial failure/i)).not.toBeInTheDocument();
  });
});
