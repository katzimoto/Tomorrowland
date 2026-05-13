import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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
    indexed: 1,
    skipped: 0,
    failed: 0,
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

  it("opens the Add Source dialog on button click", async () => {
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    expect(await screen.findByRole("dialog", { name: /add source/i })).toBeInTheDocument();
  });

  it("renders folder path field when folder type is selected", async () => {
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    await screen.findByRole("dialog");
    expect(screen.getByLabelText(/folder path/i)).toBeInTheDocument();
  });

  it("renders sensitive api_token field as password input for nifi", async () => {
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    await screen.findByRole("dialog");

    const typeSelect = screen.getByLabelText(/type/i);
    await user.selectOptions(typeSelect, "nifi");

    const tokenInput = screen.getByLabelText(/api token/i);
    expect(tokenInput).toHaveAttribute("type", "password");
  });

  it("calls createSource and closes dialog on valid submit", async () => {
    vi.mocked(adminApi.adminApi.createSource).mockResolvedValue({
      ...sourceDefaults,
      id: "new-1",
      name: "My Folder",
      type: "folder",
      path: "/tmp",
    });
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    await screen.findByRole("dialog");

    await user.type(screen.getByLabelText(/name/i), "My Folder");
    await user.type(screen.getByLabelText(/folder path/i), "/tmp/docs");
    await user.click(screen.getByRole("button", { name: /save source/i }));

    await waitFor(() => {
      expect(adminApi.adminApi.createSource).toHaveBeenCalledWith(
        expect.objectContaining({ name: "My Folder", type: "folder" }),
        expect.anything(),
      );
    });
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
      indexed: 3,
      skipped: 0,
      failed: 0,
    });

    render(<AdminSourcesPage />);

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/Source path does not exist/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^sync$/i }));

    expect(await screen.findByText(/Indexed: 3/i)).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
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
  });
});
